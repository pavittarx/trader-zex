"""
main.py — entry point for the Fyers HMM Market Regime Screener.

Usage
-----
    uv run main.py
    uv run main.py --symbols NSE:RELIANCE-EQ NSE:TCS-EQ --timeframes 15 60 D
"""

import argparse
import logging

import config
from fyers_client import FyersClient
from screener import Screener

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

_W = 72


def run_screener(args: argparse.Namespace, client: FyersClient) -> None:
    print("\nRunning regime screener …\n")
    regimes, signals, levels = Screener(client).run(
        symbols=args.symbols,
        timeframes=args.timeframes,
    )

    print("=" * _W)
    print("  HMM REGIME")
    print("=" * _W)
    print(regimes.to_string())
    print()
    print("Legend:  ▲ Bullish  |  — Sideways  |  ▼ Bearish  |  ✕ Error")

    print()
    print("=" * _W)
    print(
        f"  CONFLUENCE SIGNALS  (structure method: {config.STRUCTURE_METHOD.upper()})"
    )
    print("=" * _W)
    print(signals.to_string())
    print()
    print("Signals:  ★ STRONG BUY/SELL  |  ↑ WEAK BUY  |  ⊙ TAKE PROFIT")
    print("          ◎ WATCH  |  · NEUTRAL  |  ⏸ WAIT  |  ✕ AVOID")

    print()
    print("=" * _W)
    print(
        f"  PRICE LEVELS  (ref: {args.timeframes[-1]} timeframe, method: {config.STRUCTURE_METHOD.upper()})"
    )
    print("=" * _W)
    print(levels.to_string())
    print("=" * _W)
    print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fyers HMM Market Regime Screener",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=config.DEFAULT_SYMBOLS,
        metavar="SYM",
        help="Fyers symbols to screen (default: config.DEFAULT_SYMBOLS)",
    )
    parser.add_argument(
        "--timeframes",
        nargs="+",
        default=config.DEFAULT_TIMEFRAMES,
        metavar="TF",
        help='Timeframes to screen, e.g. "5 15 60 D" (default: config.DEFAULT_TIMEFRAMES)',
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    client = FyersClient()
    run_screener(args, client)


if __name__ == "__main__":
    main()
