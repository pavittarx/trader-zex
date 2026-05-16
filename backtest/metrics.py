"""
metrics.py — Post-backtest performance reporting.

Takes a list of BacktestResult objects (one per symbol) and produces:
  - A summary DataFrame (one row per symbol)
  - Aggregate statistics across all symbols
  - A pretty-printed console table

Metrics reported
----------------
  Total return %
  Sharpe ratio (annualised, 252 days × 26 bars/day for 15-min)
  Max drawdown %
  Win rate %
  Profit factor
  Trade count
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from backtest.engine import BacktestResult

log = logging.getLogger(__name__)

_BARS_PER_YEAR = 252 * 26   # 15-min bars in a trading year


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

    print("\n" + "=" * 72)
    print("  BACKTEST RESULTS")
    print("=" * 72)
    print(df.to_string())
    print("=" * 72)

    # Aggregate stats
    numeric_cols = df.select_dtypes(include="number").columns
    if len(df) > 1 and len(numeric_cols) > 0:
        print("\nAggregate (mean across symbols):")
        print(df[numeric_cols].mean().to_string())
    print()


def _extract_row(r: BacktestResult) -> dict:
    row = {
        "symbol": r.symbol,
        "trades": r.trade_count,
        "date_from": str(r.date_from),
        "date_to": str(r.date_to),
    }

    # Pull from returns_stats if populated by NT analyzer
    rs = r.returns_stats or {}
    row["sharpe"] = _round(rs.get("Sharpe ratio", rs.get("SharpeRatio")))
    row["sortino"] = _round(rs.get("Sortino ratio", rs.get("SortinoRatio")))

    # Compute from fills report if available
    if r.report_df is not None and not r.report_df.empty:
        fills_metrics = _from_fills(r.report_df)
        row.update(fills_metrics)
    else:
        row.update({"total_return_pct": None, "win_rate_pct": None,
                    "max_drawdown_pct": None, "profit_factor": None})

    return row


def _from_fills(fills: pd.DataFrame) -> dict:
    """Derive basic metrics from a NautilusTrader order fills report."""
    metrics: dict = {}
    try:
        if "realized_pnl" in fills.columns:
            pnls = fills["realized_pnl"].dropna().astype(float)
        elif "commission" in fills.columns:
            # Fallback: no P&L column available
            return metrics
        else:
            return metrics

        wins = pnls[pnls > 0]
        losses = pnls[pnls < 0]

        metrics["win_rate_pct"] = round(len(wins) / len(pnls) * 100, 1) if len(pnls) > 0 else None
        metrics["total_return_pct"] = round(pnls.sum(), 2)   # absolute ₹ P&L
        metrics["profit_factor"] = (
            round(wins.sum() / abs(losses.sum()), 2)
            if losses.sum() != 0 else None
        )

        # Simple drawdown from cumulative P&L
        cum = pnls.cumsum()
        roll_max = cum.cummax()
        dd = (cum - roll_max)
        metrics["max_drawdown_pct"] = round(float(dd.min()), 2)

    except Exception as exc:
        log.debug("fills metrics extraction failed: %s", exc)

    return metrics


def _round(val) -> float | None:
    try:
        return round(float(val), 3)
    except (TypeError, ValueError):
        return None
