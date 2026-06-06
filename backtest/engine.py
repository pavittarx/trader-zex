"""
engine.py — BacktestEngine setup and backtest runners.

Usage
-----
    # Single-symbol (legacy):
    from backtest.engine import run_backtest
    result = run_backtest(client, fyers_sym="NSE:RELIANCE-EQ", ...)

    # Multi-symbol portfolio (shared capital, no survivorship bias from capital):
    from backtest.engine import run_backtest_portfolio
    results = run_backtest_portfolio(client, fyers_syms=["NSE:RELIANCE-EQ", ...], ...)
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

from core import config
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
    pnl_stats: dict       # reserved for future NT stats
    returns_stats: dict   # reserved for future NT stats
    report_df: pd.DataFrame | None = None  # per-position positions report


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
            prob_slippage=1.0,     # always model slippage (was 0.5 — decorative)
            random_seed=None,      # remove fixed seed so slippage varies across runs
        ),
    )
    return engine


def run_backtest(
    client,
    fyers_sym: str,
    date_from: date | None = None,
    date_to: date | None = None,
    log_level: str = "WARNING",
    allow_shorts: bool = config.BACKTEST_ALLOW_SHORTS,
) -> BacktestResult:
    """
    Run a full backtest for a single symbol.

    Parameters
    ----------
    client      : FyersClient instance
    fyers_sym   : e.g. "NSE:RELIANCE-EQ"
    date_from   : start of backtest window (default: 90 days ago)
    date_to     : end of backtest window (default: today)
    log_level   : NautilusTrader internal log verbosity
    allow_shorts: whether to enable short-selling (default from config)

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
        allow_shorts=allow_shorts,
    )
    strategy = HMMConfluenceStrategy(config=strategy_cfg)
    engine.add_strategy(strategy)

    # 6. Run
    engine.run()

    # 7. Collect results
    trade_count = strategy._trade_count
    report_df = _get_positions_report(engine)

    result = BacktestResult(
        symbol=fyers_sym,
        date_from=date_from,
        date_to=date_to,
        trade_count=trade_count,
        pnl_stats={},
        returns_stats={},
        report_df=report_df,
    )

    engine.dispose()
    return result


def run_backtest_portfolio(
    client,
    fyers_syms: list[str],
    date_from: date | None = None,
    date_to: date | None = None,
    log_level: str = "WARNING",
    allow_shorts: bool = config.BACKTEST_ALLOW_SHORTS,
    commission_buy: float | None = None,
    commission_sell: float | None = None,
) -> dict[str, BacktestResult]:
    """
    Run a portfolio backtest: all symbols share one engine and one ₹10L account.

    Each symbol gets its own HMMConfluenceStrategy instance with a unique
    strategy_id. The engine runs once covering all symbols together, which
    means capital is shared and reflects real portfolio-level constraints.

    Parameters
    ----------
    client          : FyersClient instance
    fyers_syms      : list of Fyers symbols, e.g. ["NSE:RELIANCE-EQ", ...]
    date_from       : start of backtest window (default: 90 days ago)
    date_to         : end of backtest window (default: today)
    log_level       : NautilusTrader internal log verbosity
    allow_shorts    : whether to enable short-selling (default from config)
    commission_buy  : override buy-leg commission rate (default: config value)
    commission_sell : override sell-leg commission rate (default: config value)

    Returns
    -------
    dict[str, BacktestResult] keyed by Fyers symbol.
    """
    if date_to is None:
        date_to = date.today()
    if date_from is None:
        date_from = date_to - timedelta(days=90)

    log.info("Portfolio backtest: %d symbols [%s → %s]", len(fyers_syms), date_from, date_to)

    # 1. Build a single engine for the whole portfolio
    engine = build_engine(log_level=log_level)

    strategies: dict[str, HMMConfluenceStrategy] = {}
    symbols_added: list[str] = []

    for fyers_sym in fyers_syms:
        ticker = fyers_sym.split(":", 1)[-1]
        strategy_id = f"hmm-{ticker}"

        log.info("  [%s] Fetching data …", fyers_sym)
        try:
            df_15m = client.get_history(fyers_sym, "15", date_from=date_from, date_to=date_to)
            df_60m = client.get_history(fyers_sym, "60", date_from=date_from, date_to=date_to)
        except Exception as exc:
            log.warning("  [%s] Data fetch failed: %s — skipping", fyers_sym, exc)
            continue

        if df_15m.empty:
            log.warning("  [%s] No 15-min data — skipping", fyers_sym)
            continue

        # Pre-compute rolling signals
        cache_key = make_cache_key(fyers_sym, date_from, date_to)
        signals_df = compute_rolling_signals(df_15m, df_60m, cache_key=cache_key)

        if signals_df.empty:
            log.warning("  [%s] No signals — skipping", fyers_sym)
            continue

        signal_records = {
            str(ts): row.to_dict() for ts, row in signals_df.iterrows()
        }

        # Add instrument and bar data to the shared engine
        # Pass commission overrides if provided (used by sensitivity sweep)
        instrument = make_equity(
            fyers_sym,
            commission_buy=commission_buy if commission_buy is not None else config.BACKTEST_COMMISSION_BUY,
            commission_sell=commission_sell if commission_sell is not None else config.BACKTEST_COMMISSION_SELL,
        )
        engine.add_instrument(instrument)

        bar_type_15m = make_bar_type(instrument.id, "15")
        engine.add_data(df_to_bars(df_15m, bar_type_15m, "15"))

        # Create strategy with unique strategy_id
        strategy_cfg = HMMStrategyConfig(
            strategy_id=strategy_id,
            instrument_id=str(instrument.id),
            bar_type_15m=str(bar_type_15m),
            signal_records=signal_records,
            allow_shorts=allow_shorts,
        )
        strategy = HMMConfluenceStrategy(config=strategy_cfg)
        engine.add_strategy(strategy)

        strategies[fyers_sym] = strategy
        symbols_added.append(fyers_sym)

    if not strategies:
        log.warning("No symbols could be loaded — returning empty results")
        engine.dispose()
        return {}

    # 2. Run all strategies in one shared engine pass
    log.info("Running portfolio engine for %d symbols …", len(symbols_added))
    engine.run()

    # 3. Extract per-symbol results from the positions report
    positions_report = _get_positions_report(engine)

    results: dict[str, BacktestResult] = {}
    for fyers_sym in symbols_added:
        strategy = strategies[fyers_sym]
        instrument_id_str = str(fyers_to_instrument_id(fyers_sym))

        # Filter positions report to this symbol
        sym_report: pd.DataFrame | None = None
        if positions_report is not None and not positions_report.empty:
            if "instrument_id" in positions_report.columns:
                mask = positions_report["instrument_id"].astype(str) == instrument_id_str
                sym_report = positions_report[mask].copy()
                if sym_report.empty:
                    sym_report = None

        results[fyers_sym] = BacktestResult(
            symbol=fyers_sym,
            date_from=date_from,
            date_to=date_to,
            trade_count=strategy._trade_count,
            pnl_stats={},
            returns_stats={},
            report_df=sym_report,
        )

    engine.dispose()
    return results


def _get_positions_report(engine: BacktestEngine) -> pd.DataFrame | None:
    """
    Retrieve the positions report from the backtest engine.

    NT 1.226: generate_positions_report() returns a DataFrame with columns:
        instrument_id, realized_pnl (string "2910.00 INR"), realized_return,
        avg_px_open, avg_px_close, duration_ns, entry, commissions
    """
    try:
        return engine.trader.generate_positions_report()
    except Exception as exc:
        log.debug("positions report failed: %s", exc)
        return None
