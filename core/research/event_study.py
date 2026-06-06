"""Generic event-study primitives — events in, reaction/drift/IC out.

Strategy-agnostic: PEAD feeds earnings dates; any future event strategy
(index rebalances, block deals, ...) feeds its own dates into the same
machinery. This is what makes "run the same test on two strategies" real.

reaction_events/tercile_bounds/in_bucket originated in pead_core.py but are
not PEAD-specific; they moved here so other strategies can use them.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.research.stats import spearman_ic, t_stat


def reaction_events(close: pd.Series, dates, frm=None) -> dict[str, float]:
    """Map each event's reaction day -> reaction return.

    The reaction day is the first trading session STRICTLY AFTER the event
    (announcements land after-hours; the market reacts next session). Key =
    reaction-day ISO date; value = reaction-day return (close[t]/close[t-1]-1).
    """
    idx = close.index
    out: dict[str, float] = {}
    lo = pd.Timestamp(frm) if frm is not None else None
    for d in dates:
        if lo is not None and d < lo:
            continue
        t = idx.searchsorted(d, side="right")
        if t < 1 or t >= len(close):
            continue
        out[idx[t].date().isoformat()] = float(close.iloc[t] / close.iloc[t - 1] - 1)
    return out


def events_with_drift(close: pd.Series, dates, horizons: list[int]) -> list[dict]:
    """Per event: reaction return + drift over each horizon, no look-ahead.

    (Extracted from scripts/pead_event_ic.py events_for().)
    """
    idx = close.index
    out = []
    for d in dates:
        t = idx.searchsorted(d, side="right")
        if t < 1 or t >= len(idx):
            continue
        rec = {"reaction": float(close.iloc[t] / close.iloc[t - 1] - 1), "date": idx[t]}
        ok = True
        for h in horizons:
            if t + h >= len(close):
                ok = False
                break
            rec[f"drift_{h}"] = float(close.iloc[t + h] / close.iloc[t] - 1)
        if ok:
            out.append(rec)
    return out


def event_ic_report(events: pd.DataFrame, horizons: list[int]) -> pd.DataFrame:
    """Pooled Spearman IC(reaction, drift_h) + sign-based L/S per horizon.

    events: DataFrame with columns reaction, drift_<h> (from events_with_drift).
    Positive IC = the reaction continues (underreaction/drift).
    """
    rows = []
    for h in horizons:
        col = f"drift_{h}"
        sub = events[["reaction", col]].dropna()
        if len(sub) < 20:
            continue
        ic, ic_t = spearman_ic(sub["reaction"], sub[col])
        sign = np.sign(sub["reaction"])
        ls = (sub[col] * sign)[sign != 0]
        rows.append({"horizon": h, "ic": ic, "ic_t": ic_t,
                     "ls_mean": float(ls.mean()), "ls_t": t_stat(ls), "n": len(ls)})
    return pd.DataFrame(rows)


def tercile_bounds(values) -> tuple[float, float]:
    """Lower/upper tercile bounds (e.g. liquidity by median daily traded value)."""
    a = np.asarray(list(values), dtype=float)
    return float(np.quantile(a, 1 / 3)), float(np.quantile(a, 2 / 3))


def in_bucket(value: float, bounds: tuple[float, float], bucket: str) -> bool:
    lo, hi = bounds
    if bucket == "low":
        return value <= lo
    if bucket == "mid":
        return lo < value <= hi
    if bucket == "high":
        return value > hi
    return True  # "all"
