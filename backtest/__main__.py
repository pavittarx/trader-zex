"""
__main__.py — CLI entry point for the backtester.

Usage
-----
    # Backtest default symbols (config.DEFAULT_SYMBOLS, no look-ahead bias):
    uv run python -m backtest

    # Backtest ALL_SYMBOLS (fixed list, fair historical comparison):
    uv run python -m backtest --all-symbols

    # Backtest specific symbols:
    uv run python -m backtest --symbols NSE:RELIANCE-EQ NSE:TCS-EQ

    # Print today's ranked stocks and EXIT (no backtest, avoids survivorship bias):
    uv run python -m backtest --use-ranker

    # Allow short-selling (off by default — Indian equity spot is long-only):
    uv run python -m backtest --allow-shorts

    # Specify date range:
    uv run python -m backtest --date-from 2024-01-01 --date-to 2024-06-30

    # Verbose NautilusTrader internal logs:
    uv run python -m backtest --log-level INFO
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta

import config
from backtest.engine import run_backtest_portfolio, BacktestResult
from backtest.metrics import print_summary
from fyers_client import FyersClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="HMM Confluence Strategy Backtester")
    p.add_argument(
        "--symbols", nargs="+", metavar="SYM",
        help="Fyers symbols to backtest (e.g. NSE:RELIANCE-EQ). "
             "Overrides --all-symbols and --use-ranker.",
    )
    p.add_argument(
        "--use-ranker", action="store_true",
        help=(
            "Print today's ranked stocks and EXIT. "
            "NOTE: using ranked symbols to then run a historical backtest would "
            "introduce look-ahead/survivorship bias — the ranker uses today's "
            "data to select winners. Use --all-symbols for fair backtesting."
        ),
    )
    p.add_argument(
        "--all-symbols", action="store_true",
        help=(
            "Backtest using config.ALL_SYMBOLS (fixed universe, no look-ahead bias). "
            "Default is config.DEFAULT_SYMBOLS."
        ),
    )
    p.add_argument(
        "--top-n", type=int, default=5,
        help="Number of long + short candidates shown by --use-ranker (default: 5 each).",
    )
    p.add_argument(
        "--date-from", type=date.fromisoformat, default=None,
        help="Backtest start date YYYY-MM-DD (default: 90 days ago).",
    )
    p.add_argument(
        "--date-to", type=date.fromisoformat, default=None,
        help="Backtest end date YYYY-MM-DD (default: today).",
    )
    p.add_argument(
        "--allow-shorts", action="store_true",
        help=(
            "Enable short-selling in the strategy. "
            "Off by default — Indian equity spot markets do not support short selling "
            "without F&O or BTST arrangements."
        ),
    )
    p.add_argument(
        "--log-level", default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="NautilusTrader internal log level.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    client = FyersClient()

    # --use-ranker: print rankings and EXIT (no backtest)
    if args.use_ranker:
        from ranker import StockRanker
        log.info("Running ranker to select top-%d symbols …", args.top_n)
        ranker = StockRanker(client, n_top=args.top_n)
        result = ranker.rank()

        print(f"\n{'='*70}")
        print(f"  TODAY'S RANKED STOCKS — {date.today()}  (top {args.top_n} per side)")
        print(f"{'='*70}")
        print()
        print("  NOTE: These rankings are based on TODAY'S market data.")
        print("  Using them to select symbols for a HISTORICAL backtest")
        print("  introduces look-ahead / survivorship bias.")
        print("  Use --all-symbols for a fair historical backtest.")
        print()

        print(f"  LONG CANDIDATES ({len(result.long)})")
        print(f"  {'─'*65}")
        for r in result.long:
            print(f"  {r}")

        print(f"\n  SHORT CANDIDATES ({len(result.short)})")
        print(f"  {'─'*65}")
        for r in result.short:
            print(f"  {r}")

        print()
        sys.exit(0)

    # Resolve date range
    date_to = args.date_to or date.today()
    date_from = args.date_from or (date_to - timedelta(days=90))

    # Resolve symbol list
    if args.symbols:
        symbols = args.symbols
        log.info("Backtesting %d symbol(s): %s", len(symbols), symbols)
    elif args.all_symbols:
        symbols = config.ALL_SYMBOLS
        log.info("Using ALL_SYMBOLS (%d) for fair historical backtesting", len(symbols))
    else:
        symbols = config.DEFAULT_SYMBOLS
        log.info("Using DEFAULT_SYMBOLS (%d)", len(symbols))

    allow_shorts = args.allow_shorts

    # Run portfolio backtest (shared engine, shared capital)
    results_map = run_backtest_portfolio(
        client,
        fyers_syms=symbols,
        date_from=date_from,
        date_to=date_to,
        log_level=args.log_level,
        allow_shorts=allow_shorts,
    )

    # Convert to ordered list for summary display
    results: list[BacktestResult] = []
    for sym in symbols:
        if sym in results_map:
            r = results_map[sym]
            results.append(r)
            log.info("  %s: %d trades", sym, r.trade_count)
        else:
            log.warning("  %s: no result (data fetch failed)", sym)

    # Print results table
    print_summary(results)


if __name__ == "__main__":
    main()
