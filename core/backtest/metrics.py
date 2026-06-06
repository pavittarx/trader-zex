"""
metrics.py — Post-backtest performance reporting.

Takes a list of BacktestResult objects (one per symbol) and produces:
  - A summary DataFrame (one row per symbol)
  - Aggregate statistics across all symbols
  - A pretty-printed console table

Metrics reported
----------------
  Total P&L (₹ absolute)
  Win rate %
  Profit factor
  Max drawdown (₹)
  Trade count
  Total cost (₹) — commissions parsed from positions report
  Cost as % of gross P&L+cost
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from core import config
from core.backtest.engine import BacktestResult

log = logging.getLogger(__name__)


def summarise(results: list[BacktestResult]) -> pd.DataFrame:
    """
    Build a summary DataFrame from a list of BacktestResult objects.

    Returns one row per symbol with key performance metrics.
    """
    rows = []
    for r in results:
        row = _extract_row(r)
        rows.append(row)

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.set_index("symbol")
    return df


def print_summary(results: list[BacktestResult]) -> None:
    """Print a formatted table of backtest results to stdout."""
    df = summarise(results)
    if df.empty:
        print("No results to display.")
        return

    print("\n" + "=" * 80)
    print("  BACKTEST RESULTS")
    print("=" * 80)
    # Preferred column order for readability
    preferred = [
        "trades", "date_from", "date_to",
        "total_pnl_inr", "total_return_pct", "annualized_return_pct",
        "win_rate_pct", "profit_factor",
        "max_drawdown_inr", "total_cost_inr", "cost_pct_of_gross",
        "avg_holding_bars",
    ]
    cols = [c for c in preferred if c in df.columns] + [
        c for c in df.columns if c not in preferred
    ]
    print(df[cols].to_string())
    print("=" * 80)

    # Aggregate stats
    numeric_cols = df.select_dtypes(include="number").columns
    if len(df) > 1 and len(numeric_cols) > 0:
        print("\nAggregate (mean across symbols):")
        print(df[numeric_cols].mean().to_string())

    print("\nNote: No benchmark comparison available. Run with Nifty buy-and-hold over")
    print("      the same period to judge alpha. Annualized return assumes compounding.")
    print()


def _extract_row(r: BacktestResult) -> dict:
    row = {
        "symbol": r.symbol,
        "trades": r.trade_count,
        "date_from": str(r.date_from),
        "date_to": str(r.date_to),
    }

    # Compute metrics from positions report if available
    if r.report_df is not None and not r.report_df.empty:
        pos_metrics = _from_positions(r.report_df)
        row.update(pos_metrics)
    else:
        row.update({
            "total_pnl_inr": None,
            "win_rate_pct": None,
            "max_drawdown_inr": None,
            "profit_factor": None,
            "total_cost_inr": None,
            "cost_pct_of_gross": None,
        })

    # Annualized return from total P&L
    initial_capital = config.BACKTEST_INITIAL_CAPITAL
    if r.report_df is not None and row.get("total_pnl_inr") is not None:
        total_days = (r.date_to - r.date_from).days
        if total_days > 0:
            total_return = row["total_pnl_inr"] / initial_capital
            ann_factor = 365.0 / total_days
            row["total_return_pct"] = round(total_return * 100, 2)
            row["annualized_return_pct"] = round(
                ((1 + total_return) ** ann_factor - 1) * 100, 2
            )

    return row


def _from_positions(positions_df: pd.DataFrame, instrument_id: str | None = None) -> dict:
    """
    Derive basic metrics from a NautilusTrader positions report.

    The positions report's ``realized_pnl`` column contains strings like
    "2910.00 INR". This function parses them into floats.

    Parameters
    ----------
    positions_df  : DataFrame from engine.trader.generate_positions_report()
    instrument_id : if provided, filter to this instrument_id string first
    """
    metrics: dict = {}
    try:
        df = positions_df.copy()

        if instrument_id is not None and "instrument_id" in df.columns:
            df = df[df["instrument_id"].astype(str) == instrument_id]

        if df.empty or "realized_pnl" not in df.columns:
            return metrics

        # Sort by close time if available so equity curve and drawdown are correct
        for col in ("ts_closed", "ts_last", "closed"):
            if col in df.columns:
                try:
                    df = df.sort_values(col)
                except Exception:
                    pass
                break

        # Parse "2910.00 INR" → 2910.0
        def _parse_pnl(val) -> float:
            try:
                return float(str(val).split()[0])
            except (ValueError, IndexError):
                return float("nan")

        pnls = df["realized_pnl"].apply(_parse_pnl).dropna()

        if pnls.empty:
            return metrics

        wins = pnls[pnls > 0]
        losses = pnls[pnls < 0]

        metrics["win_rate_pct"] = (
            round(len(wins) / len(pnls) * 100, 1) if len(pnls) > 0 else None
        )
        metrics["total_pnl_inr"] = round(float(pnls.sum()), 2)
        metrics["profit_factor"] = (
            round(float(wins.sum()) / float(abs(losses.sum())), 2)
            if losses.sum() != 0 else None
        )

        # Drawdown from cumulative P&L curve
        cum = pnls.cumsum()
        roll_max = cum.cummax()
        dd = cum - roll_max
        metrics["max_drawdown_inr"] = round(float(dd.min()), 2)

        # Parse commissions. NT 1.226 reports this as a list of Money strings,
        # e.g. ['740.42 INR'] (one entry per currency). Sum all entries per row.
        if "commissions" in df.columns:
            def _parse_cost(val) -> float:
                items = val if isinstance(val, (list, tuple)) else [val]
                total = 0.0
                found = False
                for item in items:
                    try:
                        total += float(str(item).strip("[]'\" ").split()[0])
                        found = True
                    except (ValueError, IndexError):
                        continue
                return total if found else float("nan")
            costs = df["commissions"].apply(_parse_cost).dropna()
            metrics["total_cost_inr"] = round(float(costs.sum()), 2)
            gross = abs(metrics.get("total_pnl_inr") or 0) + float(costs.sum())
            if gross > 0:
                metrics["cost_pct_of_gross"] = round(float(costs.sum()) / gross * 100, 1)

        # Average holding duration in 15-min bars
        if "duration_ns" in df.columns:
            avg_duration_ns = df["duration_ns"].dropna().mean()
            if not pd.isna(avg_duration_ns):
                # Convert nanoseconds to 15-min bars (1 bar = 15 * 60 * 1e9 ns)
                metrics["avg_holding_bars"] = round(float(avg_duration_ns) / (15 * 60 * 1e9), 1)

    except Exception as exc:
        log.debug("positions metrics extraction failed: %s", exc)

    return metrics


def _round(val) -> float | None:
    try:
        return round(float(val), 3)
    except (TypeError, ValueError):
        return None
