"""
__main__.py — CLI entry point for the backtester.

Usage
-----
    # Backtest using today's top-ranked symbols (default):
    uv run python -m backtest

    # Backtest specific symbols:
    uv run python -m backtest --symbols NSE:RELIANCE-EQ NSE:TCS-EQ

    # Specify date range:
    uv run python -m backtest --date-from 2024-01-01 --date-to 2024-06-30

    # Use the ranker to select symbols, backtest top-N per side:
    uv run python -m backtest --use-ranker --top-n 5

    # Verbose NautilusTrader internal logs:
    uv run python -m backtest --log-level INFO
"""

from __future__ import annotations

import argparse
import logging
from datetime import date, timedelta

import config
from backtest.engine import run_backtest, BacktestResult
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
             "Overrides --use-ranker.",
    )
    p.add_argument(
        "--use-ranker", action="store_true",
        help="Use today's ranked stocks as the symbol list.",
    )
    p.add_argument(
        "--top-n", type=int, default=5,
        help="Number of long + short candidates from ranker (default: 5 each).",
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
        "--log-level", default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="NautilusTrader internal log level.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    date_to = args.date_to or date.today()
    date_from = args.date_from or (date_to - timedelta(days=90))

    client = FyersClient()

    # Resolve symbol list
    if args.symbols:
        symbols = args.symbols
        log.info("Backtesting %d symbol(s): %s", len(symbols), symbols)
    elif args.use_ranker:
        from ranker import StockRanker
        log.info("Running ranker to select top-%d symbols …", args.top_n)
        ranker = StockRanker(client, n_top=args.top_n)
        result = ranker.rank()
        symbols = [r.symbol for r in result.long[:args.top_n]] + \
                  [r.symbol for r in result.short[:args.top_n]]
        symbols = list(dict.fromkeys(symbols))  # deduplicate, preserve order
        log.info("Ranker selected %d symbols: %s", len(symbols), symbols)
    else:
        symbols = config.DEFAULT_SYMBOLS
        log.info("Using DEFAULT_SYMBOLS (%d)", len(symbols))

    # Run backtest for each symbol
    results: list[BacktestResult] = []
    for sym in symbols:
        try:
            r = run_backtest(
                client,
                fyers_sym=sym,
                date_from=date_from,
                date_to=date_to,
                log_level=args.log_level,
            )
            results.append(r)
            log.info("  %s: %d trades", sym, r.trade_count)
        except Exception as exc:
            log.error("  %s failed: %s", sym, exc)

    # Print results table
    print_summary(results)


if __name__ == "__main__":
    main()
