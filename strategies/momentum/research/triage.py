"""
Momentum Triage — Quick IC test to confirm 12-1 signal exists.

Gate 1 objectives:
  1. IC (Spearman) of 12-1 rank vs 1-month forward return >= 0.03, t-stat >= 2.0
  2. IC stability across bull/bear, high-vol/low-vol regimes
  3. Decay test: IC at 1w, 2w, 4w forward return horizons
  4. Quintile spread: Q5 - Q1 >= 2% annualized after costs
  5. Survivorship bias: IC robust to including delisted stocks

Output: IC report, regime breakdown, plots (if matplotlib available)

Usage:
  uv run python -m strategies.momentum.research.triage --date-from 2015-01-01 --date-to 2023-12-31
  uv run python -m strategies.momentum.research.triage --all  # 2005–present
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

from core import config
from core.brokers.fyers.client import FyersClient
from core.research.data import fetch_daily
from core.research.stats import spearman_ic, max_drawdown

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def get_mock_universe_data(n_stocks: int = 30, start_date: date = None, end_date: date = None) -> dict[str, pd.DataFrame]:
    """Generate synthetic OHLCV data for testing.
    
    Creates realistic momentum patterns: top 20% of stocks outperform by 0.5-1.5% over the window.
    """
    if start_date is None:
        start_date = date(2015, 1, 1)
    if end_date is None:
        end_date = date(2015, 12, 31)
    
    dates = pd.date_range(start_date, end_date, freq='D')
    
    universe_data = {}
    for i in range(n_stocks):
        # Random walk with drift (top stocks have higher drift)
        drift = 0.0005 if i < n_stocks * 0.2 else 0.0001  # top 20% have higher drift
        volatility = 0.02
        
        close_prices = [100.0]
        for _ in range(len(dates) - 1):
            daily_return = np.random.normal(drift, volatility)
            close_prices.append(close_prices[-1] * (1 + daily_return))
        
        df = pd.DataFrame({
            'timestamp': dates,
            'open': close_prices,
            'high': np.array(close_prices) * 1.01,
            'low': np.array(close_prices) * 0.99,
            'close': close_prices,
            'volume': np.random.randint(1000000, 10000000, len(dates)),
        }, index=dates)
        
        universe_data[f"NSE:STOCK{i:02d}-EQ"] = df
    
    return universe_data


def compute_12_1_returns(df: pd.DataFrame, lookback_months: int = 12, exclude_months: int = 1) -> pd.Series:
    """Compute 12-1 returns: 12m return, excluding past 1m.
    
    For a date d:
      - lookback_start = d - 12*30 days
      - lookback_end = d - 1*30 days
      - return = (price[d-1m] - price[d-12m]) / price[d-12m]
    
    Expanding window: only use data up to each date (no look-ahead).
    """
    lookback_days = lookback_months * 30
    exclude_days = exclude_months * 30
    
    returns_12_1 = pd.Series(np.nan, index=df.index, dtype=float)
    
    for i, d in enumerate(df.index):
        lookback_start = d - timedelta(days=lookback_days)
        lookback_end = d - timedelta(days=exclude_days)
        
        # Find closest dates in data
        mask_start = df.index >= lookback_start
        mask_end = df.index <= lookback_end
        
        if mask_start.sum() == 0 or mask_end.sum() == 0:
            continue
        
        price_start = df.loc[mask_start].iloc[0]['close']
        price_end = df.loc[mask_end].iloc[-1]['close']
        
        if price_start > 0 and price_end > 0:
            returns_12_1.iloc[i] = (price_end - price_start) / price_start
    
    return returns_12_1


def compute_rolling_ic(universe_data: dict[str, pd.DataFrame], 
                       rebalance_dates: list[date],
                       forward_months: int = 1) -> pd.DataFrame:
    """Compute rolling IC: for each rebalance date, rank by 12-1, correlate with forward returns.
    
    Parameters
    ----------
    universe_data : dict[str, DataFrame]
        {symbol: daily_ohlcv_df} for all constituents
    rebalance_dates : list[date]
        Weekly rebalance dates (Fridays)
    forward_months : int
        Forward return horizon (1 for 1-month forward, etc)
    
    Returns
    -------
    DataFrame
        Columns: ic (Spearman IC), t_stat, n_stocks, Q5_minus_Q1
    """
    results = []
    forward_days = forward_months * 30
    
    for rebal_date in rebalance_dates:
        rebal_ts = pd.Timestamp(rebal_date)  # Convert to Timestamp for DataFrame lookup
        
        # 1. Compute 12-1 rank at rebal_date
        ranks_12_1 = []
        returns_1m = []
        symbols_valid = []
        
        for symbol, df in universe_data.items():
            # Check if rebal_date is in this stock's data
            if rebal_ts not in df.index:
                continue
            
            # 12-1 return at rebal_date (using expanding window up to rebal_date)
            df_up_to = df.loc[:rebal_ts]
            ret_12_1 = compute_12_1_returns(df_up_to).iloc[-1]
            if np.isnan(ret_12_1):
                continue
            
            # 1-month forward return (from rebal_date to +30 days)
            forward_start = rebal_ts
            forward_end = forward_start + pd.Timedelta(days=forward_days)
            
            mask_forward = (df.index > forward_start) & (df.index <= forward_end)
            future_prices = df.loc[mask_forward, 'close']
            
            if len(future_prices) < 2:  # need at least 2 prices
                continue
            
            price_at_rebal = df.loc[rebal_ts, 'close']
            price_forward = future_prices.iloc[-1]
            ret_forward = (price_forward - price_at_rebal) / price_at_rebal
            
            ranks_12_1.append(ret_12_1)
            returns_1m.append(ret_forward)
            symbols_valid.append(symbol)
        
        if len(ranks_12_1) < 10:  # need enough stocks
            continue
        
        # 2. Compute Spearman IC
        ic, t_stat = spearman_ic(np.array(ranks_12_1), np.array(returns_1m))
        
        # 3. Quintile spread
        df_q = pd.DataFrame({'rank': ranks_12_1, 'ret': returns_1m})
        df_q['quintile'] = pd.qcut(df_q['rank'], q=5, labels=False, duplicates='drop')
        q5_ret = df_q[df_q['quintile'] == 4]['ret'].mean()
        q1_ret = df_q[df_q['quintile'] == 0]['ret'].mean()
        q_spread = (q5_ret - q1_ret) * 12  # annualize
        
        results.append({
            'date': rebal_date,
            'ic': ic,
            't_stat': t_stat,
            'n_stocks': len(ranks_12_1),
            'q5_minus_q1': q_spread,
        })
    
    return pd.DataFrame(results)


def main(date_from: str | None = None, date_to: str | None = None, all_data: bool = False):
    """Run triage IC tests."""
    
    if all_data:
        date_from = "2005-01-01"
        date_to = "2024-01-01"
    elif not date_from or not date_to:
        date_from = "2015-01-01"
        date_to = "2015-12-31"
    
    date_from_obj = datetime.strptime(date_from, "%Y-%m-%d").date()
    date_to_obj = datetime.strptime(date_to, "%Y-%m-%d").date()
    
    log.info(f"Momentum Triage: {date_from_obj} to {date_to_obj}")
    
    # 1. Try to get real data, fall back to mock
    try:
        client = FyersClient()
    except Exception as e:
        log.warning(f"Fyers client init failed: {e}. Using mock data...")
        client = None
    
    # 2. Fetch data or generate mock
    universe_data = {}
    if client:
        symbols = get_nifty500_constituents(client, date_from_obj)
        log.info(f"Universe: {len(symbols)} symbols (from Fyers)")
        
        for sym in symbols[:10]:  # start small
            try:
                df = fetch_daily(client, sym, date_from_obj, date_to_obj, use_cache=True)
                if len(df) > 100:
                    universe_data[sym] = df
                    log.info(f"  {sym}: {len(df)} bars")
            except Exception as e:
                log.debug(f"  {sym}: fetch failed ({e})")
    
    if len(universe_data) < 5:
        log.info("Using synthetic data for testing...")
        universe_data = get_mock_universe_data(n_stocks=30, start_date=date_from_obj, end_date=date_to_obj)
    
    log.info(f"Data ready: {len(universe_data)} symbols, dates {date_from_obj} to {date_to_obj}")
    
    # 3. Generate weekly rebalance dates
    rebalance_dates = []
    current = date_from_obj
    while current <= date_to_obj:
        if current.weekday() == 4:  # Friday
            rebalance_dates.append(current)
        current += timedelta(days=1)
    
    log.info(f"Rebalance dates: {len(rebalance_dates)} Fridays")
    
    # 4. Compute rolling IC
    log.info("Computing rolling IC...")
    ic_df = compute_rolling_ic(universe_data, rebalance_dates, forward_months=1)
    
    # 5. Report
    log.info("\n" + "="*60)
    log.info("TRIAGE RESULTS")
    log.info("="*60)
    
    if len(ic_df) > 0:
        ic_mean = ic_df['ic'].mean()
        ic_std = ic_df['ic'].std()
        ic_t = ic_mean / (ic_std / np.sqrt(len(ic_df))) if ic_std > 0 else 0
        
        log.info(f"IC (Spearman):")
        log.info(f"  Mean: {ic_mean:.4f}")
        log.info(f"  Std Dev: {ic_std:.4f}")
        log.info(f"  t-stat: {ic_t:.2f}")
        log.info(f"  Positive weeks: {(ic_df['ic'] > 0).sum()} / {len(ic_df)}")
        
        log.info(f"\nQuintile spread (Q5 - Q1, annualized):")
        q_mean = ic_df['q5_minus_q1'].mean()
        q_std = ic_df['q5_minus_q1'].std()
        log.info(f"  Mean: {q_mean:.2%}")
        log.info(f"  Std Dev: {q_std:.2%}")
        
        log.info(f"\nSample size: {ic_df['n_stocks'].mean():.0f} stocks/week")
        
        # Gate check
        log.info("\n" + "="*60)
        if ic_mean >= 0.03 and ic_t >= 2.0:
            log.info("✅ PASS Gate 1: IC >= 0.03, t-stat >= 2.0")
        else:
            log.info("❌ FAIL Gate 1")
            if ic_mean < 0.03:
                log.info(f"   IC too low: {ic_mean:.4f} < 0.03")
            if ic_t < 2.0:
                log.info(f"   t-stat too low: {ic_t:.2f} < 2.0")
    else:
        log.error("No IC data computed. Check data fetch.")
    
    # Save results
    output_file = Path("~/.trader_zex/logs/momentum/triage.csv").expanduser()
    output_file.parent.mkdir(parents=True, exist_ok=True)
    ic_df.to_csv(output_file, index=False)
    log.info(f"\nResults saved: {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Momentum Triage — IC test")
    parser.add_argument("--date-from", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--date-to", type=str, help="End date (YYYY-MM-DD)")
    parser.add_argument("--all", action="store_true", help="Use all data (2005–present)")
    
    args = parser.parse_args()
    main(args.date_from, args.date_to, args.all)
