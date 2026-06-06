"""Transaction-cost models, in return terms.

The recurring lesson (RESEARCH_BACKLOG.md): every daily-rebalance intraday
L/S we tested had a gross edge smaller than ~28%/yr of round-trip cost.
Always evaluate net.
"""
from __future__ import annotations


def leg(bps: float) -> float:
    """One-way cost as a return fraction (15 bps -> 0.0015)."""
    return bps / 1e4


def round_trip(bps_per_leg: float) -> float:
    """Round-trip cost as a return fraction (two legs)."""
    return 2 * bps_per_leg / 1e4
