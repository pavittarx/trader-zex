"""PEAD signal + risk logic — single source of truth for this strategy.

Before this module the reaction-detection and kill-switch logic were hand-copied
across ~8 scripts (a real regression risk — the t+1 alignment bug had 8 places to
reappear). Everything PEAD routes through here: the NT strategy (strategy.py),
the research scripts, and any live runner.
"""
from __future__ import annotations

import numpy as np

# Generic event-study primitives live in the shared research harness;
# re-exported here so PEAD call sites keep one import path.
from core.research.event_study import (  # noqa: F401
    in_bucket,
    reaction_events,
    tercile_bounds,
)
from strategies.pead.manifest import MANIFEST

_KC = {k.kind: k.params for k in MANIFEST.kill_criteria}


def kill_check(net_rets,
               dd_limit: float = _KC["drawdown"]["dd_limit"],
               trailing_n: int = _KC["trailing_mean"]["window"]) -> str | None:
    """Evaluate the pre-registered kill-criteria on a sequence of net per-trade
    returns (chronological). Returns the tripped criterion string, or None.

    Criteria (PEAD_PLAYBOOK.md §kill-criteria): equity drawdown, trailing-window
    mean <= 0, trailing-window win% < 45, realized mean > 2 SE below the prior.
    Same arithmetic as core.live.risk built from this manifest (test-pinned).
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
        if r.mean() < _KC["significance"]["prior_per_trade"] - 2 * se:
            return "realized mean > 2 SE below prior"
    return None
