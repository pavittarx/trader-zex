"""
engine.py — BacktestEngine setup and single-symbol backtest runner.

Usage
-----
    from backtest.engine import run_backtest
    result = run_backtest(
        client,
        fyers_sym="NSE:RELIANCE-EQ",
        date_from=date(2024, 1, 1),
        date_to=date(2024, 6, 30),
    )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd
from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.backtest.models import FillModel
from nautilus_trader.config import LoggingConfig
from nautilus_trader.model.currencies import INR
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Money

import config
from backtest.data_loader import df_to_bars, make_bar_type
from backtest.instruments import make_equity, fyers_to_instrument_id
from backtest.signal_precompute import compute_rolling_signals, make_cache_key
from backtest.strategy import HMMConfluenceStrategy, HMMStrategyConfig

log = logging.getLogger(__name__)

_NSE_VENUE = Venue("NSE")


@dataclass
class BacktestResult:
    symbol: str
    date_from: date
    date_to: date
    trade_count: int
    pnl_stats: dict       # formatted stats from NT's PortfolioAnalyzer
    returns_stats: dict   # annualised return metrics
    report_df: pd.DataFrame | None = None  # per-trade fills report


def build_engine(log_level: str = "WARNING") -> BacktestEngine:
    """Create and configure a fresh BacktestEngine for NSE equity trading."""
    cfg = BacktestEngineConfig(
        logging=LoggingConfig(log_level=log_level),
    )
    engine = BacktestEngine(config=cfg)
    engine.add_venue(
        venue=_NSE_VENUE,
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,   # MARGIN allows simulated short selling
        base_currency=INR,
        starting_balances=[Money(config.BACKTEST_INITIAL_CAPITAL, INR)],
        fill_model=FillModel(
            prob_fill_on_limit=0.5,
            prob_slippage=0.5,
            random_seed=42,
        ),
    )
    return engine


def run_backtest(
    client,
    fyers_sym: str,
    date_from: date | None = None,
    date_to: date | None = None,
    log_level: str = "WARNING",
) -> BacktestResult:
    """
    Run a full backtest for a single symbol.

    Parameters
    ----------
    client    : FyersClient instance
    fyers_sym : e.g. "NSE:RELIANCE-EQ"
    date_from : start of backtest window (default: 90 days ago)
    date_to   : end of backtest window (default: today)
    log_level : NautilusTrader internal log verbosity

    Returns
    -------
    BacktestResult with trade count and performance metrics.
    """
    if date_to is None:
        date_to = date.today()
    if date_from is None:
        date_from = date_to - timedelta(days=90)

    log.info("Backtesting %s  [%s → %s]", fyers_sym, date_from, date_to)

    # 1. Fetch historical data (15-min and 60-min)
    log.info("  Fetching 15-min data …")
    df_15m = client.get_history(fyers_sym, "15", date_from=date_from, date_to=date_to)
    log.info("  Fetching 60-min data …")
    df_60m = client.get_history(fyers_sym, "60", date_from=date_from, date_to=date_to)

    if df_15m.empty:
        log.warning("No 15-min data for %s — skipping", fyers_sym)
        return BacktestResult(
            symbol=fyers_sym, date_from=date_from, date_to=date_to,
            trade_count=0, pnl_stats={}, returns_stats={},
        )

    # 2. Pre-compute rolling signals (cached to disk)
    cache_key = make_cache_key(fyers_sym, date_from, date_to)
    log.info("  Computing rolling signals (cache_key=%s) …", cache_key)
    signals_df = compute_rolling_signals(df_15m, df_60m, cache_key=cache_key)

    if signals_df.empty:
        log.warning("No signals generated for %s — insufficient data", fyers_sym)
        return BacktestResult(
            symbol=fyers_sym, date_from=date_from, date_to=date_to,
            trade_count=0, pnl_stats={}, returns_stats={},
        )

    # Convert signal DataFrame to dict[str, dict] for NT config serialisation
    signal_records = {
        str(ts): row.to_dict() for ts, row in signals_df.iterrows()
    }

    # 3. Build engine + add instrument
    engine = build_engine(log_level=log_level)
    instrument = make_equity(fyers_sym)
    engine.add_instrument(instrument)

    # 4. Load bar data
    bar_type_15m = make_bar_type(instrument.id, "15")
    bars_15m = df_to_bars(df_15m, bar_type_15m, "15")
    engine.add_data(bars_15m)

    # 5. Add strategy
    strategy_cfg = HMMStrategyConfig(
        instrument_id=str(instrument.id),
        bar_type_15m=str(bar_type_15m),
        signal_records=signal_records,
    )
    strategy = HMMConfluenceStrategy(config=strategy_cfg)
    engine.add_strategy(strategy)

    # 6. Run
    engine.run()

    # 7. Collect results
    trade_count = strategy._trade_count
    pnl_stats = _safe_stats(engine.trader.generate_order_fills_report)
    returns_stats = _safe_returns(engine)

    result = BacktestResult(
        symbol=fyers_sym,
        date_from=date_from,
        date_to=date_to,
        trade_count=trade_count,
        pnl_stats=pnl_stats,
        returns_stats=returns_stats,
        report_df=_safe_fills_report(engine),
    )

    engine.dispose()
    return result


def _safe_stats(fn) -> dict:
    try:
        return fn() or {}
    except Exception:
        return {}


def _safe_returns(engine: BacktestEngine) -> dict:
    try:
        analyzer = engine.trader.analyzer
        stats = {}
        for k, v in analyzer.get_performance_stats_returns().items():
            stats[k] = v
        return stats
    except Exception:
        return {}


def _safe_fills_report(engine: BacktestEngine) -> pd.DataFrame | None:
    try:
        return engine.trader.generate_order_fills_report()
    except Exception:
        return None
