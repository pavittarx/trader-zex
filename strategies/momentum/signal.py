"""
Momentum Signal — 12-1 window with expanding window (no look-ahead bias).

Computes daily 12-1 returns for all symbols in a universe,
ranks them, and caches signals for backtesting.

Gate 2 objective:
  - Vectorized signal computation (fast enough for daily runs)
  - Expanding window (no future data leakage)
  - Cache signals by symbol/date for reuse
  - Validate no look-ahead bias in backtests
"""
from __future__ import annotations

from datetime import date, timedelta
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from core import config
from strategies.momentum import manifest
from strategies.momentum.research.universe_registry import universe_symbols_at_date

log = logging.getLogger(__name__)

# Signal cache: {symbol: {date: (rank, 12_1_return, forward_return)}}
_SIGNAL_CACHE_DIR = Path("~/.trader_zex/cache/momentum/signals").expanduser()


def _cache_path(
    date_from: date,
    date_to: date,
    symbols: list[str],
    lookback_months: int,
    exclude_months: int,
) -> Path:
    """Parquet file path for signal cache."""
    import hashlib

    symbols_key = ",".join(sorted(symbols))
    key = f"signals_{date_from}_{date_to}_{lookback_months}_{exclude_months}_{symbols_key}"
    fname = hashlib.md5(key.encode()).hexdigest()[:16]
    return _SIGNAL_CACHE_DIR / f"{fname}.parquet"


def compute_12_1_returns(close_series: pd.Series, 
                         lookback_months: int = 12,
                         exclude_months: int = 1) -> pd.Series:
    """
    12-1 return: 12-month return excluding past 1 month.
    
    For each date d:
      lookback_start = d - 12*21 trading days
      lookback_end = d - 1*21 trading days
      return = (price[d-1m] - price[d-12m]) / price[d-12m]
    
    Uses EXPANDING window — no future data beyond current date.
    
    Parameters
    ----------
    close_series : pd.Series
        Daily close prices, index = dates
    lookback_months : int
        12 (standard)
    exclude_months : int
        1 (standard)
    
    Returns
    -------
    pd.Series
        12-1 return at each date (NaN before lookback_months)
    """
    lookback_days = lookback_months * 21
    exclude_days = exclude_months * 21
    
    returns = pd.Series(np.nan, index=close_series.index)
    
    for i in range(len(close_series)):
        # Require full lookback + exclusion window; no partial-window bootstrap.
        if i < lookback_days or i < exclude_days:
            continue

        start_idx = i - lookback_days
        end_idx = i - exclude_days

        if start_idx >= end_idx:
            continue

        price_start = close_series.iloc[start_idx]
        price_end = close_series.iloc[end_idx]

        if price_start > 0:
            returns.iloc[i] = (price_end - price_start) / price_start
    
    return returns


def compute_signal_universe(universe_data: dict[str, pd.DataFrame],
                           date_from: date,
                           date_to: date,
                           use_pit_universe: bool = True) -> pd.DataFrame:
    """
    Compute 12-1 ranks for all symbols on all dates.
    
    Output: DataFrame with index=date, columns=symbol, values=rank (0-100).
    Rank 100 = top quintile (highest 12-1 return).
    
    Uses expanding window — signal on date d only uses data up to d.
    
    Parameters
    ----------
    universe_data : dict[str, DataFrame]
        {symbol: daily_ohlcv_df} where df has 'close' column
    date_from : date
        Start date
    date_to : date
        End date
    
    Returns
    -------
    DataFrame
        Index: DatetimeIndex (date_from to date_to)
        Columns: symbol names
        Values: percentile rank (0-100) of 12-1 return within that day's universe
    """
    # Align all series to common date range
    dates = pd.date_range(date_from, date_to, freq='D')
    
    signals = pd.DataFrame(index=dates)
    
    for symbol, df in universe_data.items():
        # Compute 12-1 for this symbol
        ret_12_1 = compute_12_1_returns(df['close'])
        
        # Align to common dates
        ret_aligned = ret_12_1.reindex(dates)
        
        signals[symbol] = ret_aligned
    
    # On each date, rank symbols by 12-1 return (0-100 percentile)
    ranked = signals.rank(axis=1, pct=True) * 100

    if use_pit_universe:
        sparse_days = 0
        for ts in ranked.index:
            pit_symbols = set(universe_symbols_at_date(ts.date()))
            if not pit_symbols:
                continue

            day_non_na = set(ranked.loc[ts].dropna().index)
            if not day_non_na:
                continue

            # Guardrail: if PIT registry is still sparse/incomplete, skip masking for that day.
            overlap = day_non_na & pit_symbols
            min_overlap = min(50, max(5, int(len(day_non_na) * 0.5)))
            if len(overlap) < min_overlap:
                sparse_days += 1
                continue

            out_of_universe = list(day_non_na - pit_symbols)
            if out_of_universe:
                ranked.loc[ts, out_of_universe] = np.nan

        if sparse_days > 0:
            log.warning(
                "PIT registry too sparse on %d days; fell back to data-available universe for those days",
                sparse_days,
            )
    
    return ranked


def get_target_portfolio(signals: pd.DataFrame, 
                         date: pd.Timestamp,
                         top_pct: float = 0.20) -> set[str]:
    """
    Target portfolio: top quintile of 12-1 ranks on a given date.
    
    Parameters
    ----------
    signals : pd.DataFrame
        Index=date, columns=symbol, values=rank (0-100)
    date : pd.Timestamp
        Rebalance date
    top_pct : float
        Percentile threshold (0.20 = top quintile)
    
    Returns
    -------
    set[str]
        Symbols in top quintile on this date
    """
    if date not in signals.index:
        return set()
    
    day_ranks = signals.loc[date]
    day_ranks = day_ranks.dropna()
    
    threshold = day_ranks.quantile(1 - top_pct)
    target = set(day_ranks[day_ranks >= threshold].index)
    
    return target


def compute_portfolio_returns(universe_data: dict[str, pd.DataFrame],
                             signals: pd.DataFrame,
                             rebalance_dates: list[date],
                             turnover_pct: float = 1.5,
                             top_pct: float = 0.20) -> pd.DataFrame:
    """
    Simulate weekly rebalance portfolio with turnover filter.
    
    On each Friday (rebalance_date):
      1. Compute target portfolio (top quintile)
      2. Skip rebalance if portfolio change < turnover_pct
      3. Compute next-week returns (forward return)
    
    Parameters
    ----------
    universe_data : dict[str, DataFrame]
        {symbol: daily_ohlcv_df}
    signals : pd.DataFrame
        Ranked signals (index=date, columns=symbol, values=rank)
    rebalance_dates : list[date]
        Weekly Friday dates
    turnover_pct : float
        Min portfolio change % to trigger rebalance (1.5% default)
    top_pct : float
        Percentile for target (0.20 = top quintile)
    
    Returns
    -------
    DataFrame
        Columns: date, target_symbols, portfolio_return, turnover, rebalanced
    """
    results = []
    current_portfolio = set()
    
    for rebal_date in rebalance_dates:
        rebal_ts = pd.Timestamp(rebal_date)
        
        # Target portfolio
        target = get_target_portfolio(signals, rebal_ts, top_pct)
        
        if not target:
            continue
        
        # Turnover check
        to_add = target - current_portfolio
        to_remove = current_portfolio - target
        turnover = len(to_add | to_remove) / max(len(current_portfolio), 1)
        
        rebalanced = turnover >= (turnover_pct / 100)
        
        if not rebalanced:
            continue  # Skip this rebalance
        
        # Next week forward return (simplified: equal weight)
        next_date = rebal_date + timedelta(days=7)
        returns_next_week = []
        
        for symbol in target:
            if symbol not in universe_data:
                continue
            
            df = universe_data[symbol]
            df_future = df[(df.index > rebal_ts) & (df.index <= pd.Timestamp(next_date))]
            
            if len(df_future) < 2:
                continue
            
            price_start = df.loc[rebal_ts, 'close'] if rebal_ts in df.index else df['close'].iloc[df.index > rebal_ts].iloc[0] if len(df[df.index > rebal_ts]) > 0 else None
            price_end = df_future['close'].iloc[-1]
            
            if price_start:
                ret = (price_end - price_start) / price_start
                returns_next_week.append(ret)
        
        if returns_next_week:
            portfolio_return = np.mean(returns_next_week)
            
            results.append({
                'date': rebal_date,
                'n_stocks': len(target),
                'portfolio_return': portfolio_return,
                'turnover': turnover,
                'rebalanced': rebalanced,
            })
        
        current_portfolio = target
    
    return pd.DataFrame(results)


def load_or_compute_signals(universe_data: dict[str, pd.DataFrame],
                           date_from: date,
                           date_to: date,
                           force_recompute: bool = False) -> pd.DataFrame:
    """
    Load cached signals or compute if missing.
    
    Parameters
    ----------
    universe_data : dict[str, DataFrame]
        {symbol: daily_ohlcv_df}
    date_from : date
        Start date
    date_to : date
        End date
    force_recompute : bool
        If True, ignore cache
    
    Returns
    -------
    pd.DataFrame
        Signal ranks (index=date, columns=symbol, values=0-100 percentile)
    """
    lookback = int(manifest.MANIFEST.params.get("lookback_months", 12))
    exclude = int(manifest.MANIFEST.params.get("ranking_months", 1))
    symbols = list(universe_data.keys())
    cache_path = _cache_path(date_from, date_to, symbols, lookback, exclude)
    
    if cache_path.exists() and not force_recompute:
        log.info(f"Loading cached signals from {cache_path}")
        return pd.read_parquet(cache_path)
    
    log.info(f"Computing signals for {len(universe_data)} symbols, {date_from} to {date_to}")
    signals = compute_signal_universe(universe_data, date_from, date_to, use_pit_universe=True)
    
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    signals.to_parquet(cache_path)
    log.info(f"Cached signals to {cache_path}")
    
    return signals


if __name__ == "__main__":
    # Test: compute signals for a sample universe
    from strategies.momentum.research.prepare_data import prepare_data
    from datetime import timedelta
    
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    
    print("Testing signal computation...\n")
    
    # Get data
    data = prepare_data(date(2024, 1, 1), date(2024, 6, 30), n_symbols=20)
    print(f"Fetched {len(data)} symbols\n")
    
    # Compute signals
    signals = load_or_compute_signals(data, date(2024, 1, 1), date(2024, 6, 30))
    print(f"Signals computed: {signals.shape}")
    print(f"Date range: {signals.index[0]} to {signals.index[-1]}")
    print(f"Sample (2024-02-01):\n{signals.loc['2024-02-01'].head(10)}\n")
    
    # Test target portfolio on a date
    test_date = pd.Timestamp("2024-02-02")
    if test_date in signals.index:
        target = get_target_portfolio(signals, test_date, top_pct=0.20)
        print(f"Target portfolio on {test_date.date()}: {len(target)} stocks")
        print(f"  {sorted(list(target))[:5]}...\n")
    
    print("✅ Signal test complete")
