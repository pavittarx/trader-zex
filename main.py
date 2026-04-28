"""
main.py — entry point for the Fyers HMM Market Regime Screener.

Modes
-----
Screener (default)
    Screen a list of symbols across multiple timeframes and print a regime table.

    uv run main.py
    uv run main.py --symbols NSE:RELIANCE-EQ NSE:TCS-EQ --timeframes 15 60 D

Plot
    Fetch history for one symbol, run the HMM, and display an interactive chart.

    uv run main.py --plot NSE:RELIANCE-EQ
    uv run main.py --plot NSE:RELIANCE-EQ --timeframe 60 --backend matplotlib
"""

import argparse
import logging
import sys

import config
from fyers_client import INTRADAY_RESOLUTIONS, RESAMPLE_RULES, FyersClient, resample_ohlcv
from hmm_model import HMMModel
from screener import Screener
from visualization import plot_matplotlib, plot_plotly

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Modes
# ------------------------------------------------------------------

def run_screener(args: argparse.Namespace, client: FyersClient) -> None:
    print("\nRunning regime screener …\n")
    table = Screener(client).run(
        symbols=args.symbols,
        timeframes=args.timeframes,
    )
    print("=" * 60)
    print("  REGIME SCREENER RESULTS")
    print("=" * 60)
    print(table.to_string())
    print("=" * 60)
    print("\nLegend:  ▲ Bullish  |  — Sideways  |  ▼ Bearish  |  ✕ Error\n")

    _prompt_plot(args, client)


def _prompt_plot(args: argparse.Namespace, client: FyersClient) -> None:
    """After the screener table, interactively offer to plot any symbol."""
    symbols = args.symbols
    timeframes = args.timeframes

    print("─" * 60)
    print("  VISUALIZE A SYMBOL")
    print("─" * 60)
    print(f"  Available symbols  : {', '.join(s.split(':')[1].replace('-EQ','') for s in symbols)}")
    print(f"  Available timeframes: {', '.join(timeframes)}")
    print("  Press Enter to skip.\n")

    raw_sym = input("  Symbol to plot (e.g. RELIANCE): ").strip().upper()
    if not raw_sym:
        return

    # Accept short names like "RELIANCE" or full "NSE:RELIANCE-EQ"
    if ":" not in raw_sym:
        raw_sym = f"NSE:{raw_sym}-EQ"

    raw_tf = input(f"  Timeframe [{timeframes[-1]}]: ").strip() or timeframes[-1]
    backend = input("  Backend — plotly / matplotlib [plotly]: ").strip().lower() or "plotly"
    if backend not in ("plotly", "matplotlib"):
        backend = "plotly"

    _do_plot(client, symbol=raw_sym, tf=raw_tf, backend=backend)


def run_plot(args: argparse.Namespace, client: FyersClient) -> None:
    _do_plot(client, symbol=args.plot, tf=args.timeframe, backend=args.backend)


def _do_plot(client: FyersClient, *, symbol: str, tf: str, backend: str = "plotly") -> None:
    if tf in INTRADAY_RESOLUTIONS:
        log.info("Fetching 1-min data for %s and resampling to %s …", symbol, tf)
        base = client.get_history(symbol, "1")
        data = resample_ohlcv(base, RESAMPLE_RULES[tf])
    else:
        log.info("Fetching %s @ %s …", symbol, tf)
        data = client.get_history(symbol, tf)

    if data.empty:
        print(f"No data returned for {symbol} @ {tf}. Check your symbol name.")
        return

    log.info("Fitting HMM on %d bars …", len(data))
    result = HMMModel().detect_regime(data)

    print(f"\nCurrent regime  →  {symbol} [{tf}]: {result.current_regime}")
    if not result.converged:
        print("  Warning: HMM did not fully converge — treat this result with caution.")

    if backend == "matplotlib":
        import matplotlib.pyplot as plt
        fig = plot_matplotlib(data, result, symbol=symbol, timeframe=tf)
        plt.show()
    else:
        fig = plot_plotly(data, result, symbol=symbol, timeframe=tf)
        fig.show()


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fyers HMM Market Regime Screener",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # --- Screener options ---
    parser.add_argument(
        "--symbols", nargs="+", default=config.DEFAULT_SYMBOLS,
        metavar="SYM",
        help="Fyers symbols to screen (default: config.DEFAULT_SYMBOLS)",
    )
    parser.add_argument(
        "--timeframes", nargs="+", default=config.DEFAULT_TIMEFRAMES,
        metavar="TF",
        help='Timeframes to screen, e.g. "5 15 60 D" (default: config.DEFAULT_TIMEFRAMES)',
    )

    # --- Plot mode ---
    parser.add_argument(
        "--plot", metavar="SYMBOL", default=None,
        help="Plot regime chart for a single symbol (skips screener)",
    )
    parser.add_argument(
        "--timeframe", default="D", metavar="TF",
        help="Timeframe to use in --plot mode (default: D)",
    )
    parser.add_argument(
        "--backend", choices=["plotly", "matplotlib"], default="plotly",
        help="Visualization backend for --plot mode (default: plotly)",
    )

    return parser.parse_args()


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

def main() -> None:
    args = parse_args()
    client = FyersClient()          # handles auth (cache → interactive prompt)

    if args.plot:
        run_plot(args, client)
    else:
        run_screener(args, client)


if __name__ == "__main__":
    main()
