"""pead_core.py — single source of truth for PEAD signal + risk logic.

Before this module the reaction-detection and kill-switch logic were hand-copied
across ~8 scripts (a real regression risk — the t+1 alignment bug had 8 places to
reappear). Everything PEAD now routes through here: the NT strategy
(backtest/pead_strategy.py), the research scripts, and any live runner.
"""
from __future__ import annotations

import numpy as np

from core import config
# Generic event-study primitives moved to the shared research harness;
# re-exported here so PEAD call sites keep one import path.
from core.research.event_study import (  # noqa: F401
    in_bucket,
    reaction_events,
    tercile_bounds,
)


def kill_check(net_rets, dd_limit: float = config.PEAD_KILL_DD,
               trailing_n: int = config.PEAD_KILL_TRAILING) -> str | None:
    """Evaluate the pre-registered kill-criteria on a sequence of net per-trade
    returns (chronological). Returns the tripped criterion string, or None.

    Criteria (PEAD_PLAYBOOK.md §kill-criteria): equity drawdown, trailing-window
    mean <= 0, trailing-window win% < 45, realized mean > 2 SE below the prior.
    """
    r = np.asarray(list(net_rets), dtype=float)
    if r.size == 0:
        return None
    eq = np.cumprod(1 + r)
    dd = float((eq / np.maximum.accumulate(eq) - 1).min())
    if dd <= -dd_limit:
        return f"drawdown {dd*100:.1f}% <= -{dd_limit*100:.0f}%"
    if r.size >= trailing_n:
        tr = r[-trailing_n:]
        if tr.mean() <= 0:
            return f"trailing-{trailing_n} mean <= 0"
        if (tr > 0).mean() < 0.45:
            return f"trailing-{trailing_n} win% < 45"
        se = r.std() / np.sqrt(r.size)
        if r.mean() < config.PEAD_PRIOR_PER_TRADE - 2 * se:
            return "realized mean > 2 SE below prior"
    return None


