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

    # Walk-forward validation (split date range into N windows):
    uv run python -m backtest --date-from 2024-01-01 --date-to 2024-12-31 --walk-forward 4

    # Cost sensitivity sweep (run at 0.5×, 1×, 1.5×, 2× commission):
    uv run python -m backtest --sensitivity

    # Verbose NautilusTrader internal logs:
    uv run python -m backtest --log-level INFO
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta

from core import config
from backtest.engine import run_backtest_portfolio, BacktestResult
from backtest.metrics import print_summary
from core.fyers_client import FyersClient

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
    p.add_argument(
        "--walk-forward", type=int, default=0, metavar="N",
        help=(
            "Split the date range into N equal windows and run each independently. "
            "Results should be consistent across windows; high variance = overfitting. "
            "Example: --date-from 2024-01-01 --date-to 2024-12-31 --walk-forward 4"
        ),
    )
    p.add_argument(
        "--sensitivity", action="store_true",
        help=(
            "Run backtest at 0.5×, 1×, 1.5×, and 2× the configured commission rate "
            "and print a comparison table. Strategies that flip sign within 2× cost "
            "uncertainty have no margin of safety."
        ),
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

    # --walk-forward: split date range into N windows, run each independently
    if args.walk_forward > 0:
        n = args.walk_forward
        total_days = (date_to - date_from).days
        window_days = total_days // n
        print(f"\nWalk-forward: {n} windows of ~{window_days} days each")
        print("=" * 70)

        all_window_results: list[list[BacktestResult]] = []
        for w in range(n):
            w_from = date_from + timedelta(days=w * window_days)
            w_to = (
                date_from + timedelta(days=(w + 1) * window_days)
                if w < n - 1
                else date_to
            )
            print(f"\nWindow {w+1}/{n}: {w_from} -> {w_to}")
            w_results_map = run_backtest_portfolio(
                client, fyers_syms=symbols,
                date_from=w_from, date_to=w_to,
                log_level=args.log_level, allow_shorts=allow_shorts,
            )
            w_results = [r for r in w_results_map.values()]
            all_window_results.append(w_results)
            print_summary(w_results)

        # Consistency check across windows
        print("\n" + "=" * 70)
        print("Walk-forward consistency summary:")
        for w, w_results in enumerate(all_window_results):
            total_trades = sum(r.trade_count for r in w_results)
            total_pnls = [
                r.report_df["realized_pnl"].apply(
                    lambda v: float(str(v).split()[0])
                ).sum()
                if r.report_df is not None and not r.report_df.empty
                and "realized_pnl" in r.report_df.columns
                else 0.0
                for r in w_results
            ]
            net_pnl = sum(total_pnls)
            w_from = date_from + timedelta(days=w * window_days)
            print(f"  Window {w+1}: {w_from}  trades={total_trades:3d}  net_pnl=₹{net_pnl:,.0f}")
        print()
        return  # walk-forward already printed results

    # --sensitivity: run at 0.5×, 1×, 1.5×, 2× commission and compare
    if args.sensitivity:
        base_buy = config.BACKTEST_COMMISSION_BUY
        base_sell = config.BACKTEST_COMMISSION_SELL
        multipliers = [0.5, 1.0, 1.5, 2.0]

        print(f"\nCost sensitivity sweep (base: buy={base_buy:.4f}, sell={base_sell:.4f})")
        print("=" * 70)
        print(f"  {'Multiplier':>12}  {'Buy leg':>10}  {'Sell leg':>10}  {'Trades':>7}  {'Net P&L':>12}")
        print("  " + "-" * 60)

        for mult in multipliers:
            eff_buy = base_buy * mult
            eff_sell = base_sell * mult

            sens_map = run_backtest_portfolio(
                client, fyers_syms=symbols,
                date_from=date_from, date_to=date_to,
                log_level="ERROR", allow_shorts=allow_shorts,
                commission_buy=eff_buy,
                commission_sell=eff_sell,
            )
            trades = sum(r.trade_count for r in sens_map.values())
            net_pnl = sum(
                float(str(r.report_df["realized_pnl"].iloc[0]).split()[0])
                if r.report_df is not None and not r.report_df.empty
                and "realized_pnl" in r.report_df.columns
                else 0.0
                for r in sens_map.values()
            )
            marker = " <- baseline" if mult == 1.0 else ""
            print(
                f"  {mult:>11.1f}x  {eff_buy:.4f}     "
                f"{eff_sell:.4f}    {trades:>7d}  ₹{net_pnl:>11,.0f}{marker}"
            )

        print()
        print("  Note: commissions passed explicitly to each run — exact re-simulation.")
        print("  Strategy flips sign between 1x and 2x -> no cost margin of safety.")
        print()
        return

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
