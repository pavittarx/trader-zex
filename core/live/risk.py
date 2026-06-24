"""Generic kill-switch: pre-registered criteria evaluated over realized trades.

Generalizes pead_core.kill_check (strategies/pead/PLAYBOOK.md kill-criteria) into a
registry so each strategy declares its own gates in its manifest:

    kill_criteria=[KillCriterion("drawdown", {"dd_limit": 0.08}),
                   KillCriterion("trailing_mean", {"window": 20}), ...]

All criteria take the chronological sequence of net per-trade returns and
return a tripped-reason string or None. Arithmetic is ported verbatim from
pead_core.kill_check (pinned by tests/test_risk.py).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core.manifest import Manifest


@dataclass(frozen=True)
class DrawdownCriterion:
    dd_limit: float  # e.g. 0.08 = halt at -8% equity drawdown
    name: str = "drawdown"

    def evaluate(self, r: np.ndarray) -> str | None:
        eq = np.cumprod(1 + r)
        dd = float((eq / np.maximum.accumulate(eq) - 1).min())
        if dd <= -self.dd_limit:
            return f"drawdown {dd*100:.1f}% <= -{self.dd_limit*100:.0f}%"
        return None


@dataclass(frozen=True)
class TrailingMeanCriterion:
    window: int = 20
    floor: float = 0.0
    name: str = "trailing_mean"

    def evaluate(self, r: np.ndarray) -> str | None:
        if r.size >= self.window and r[-self.window:].mean() <= self.floor:
            return f"trailing-{self.window} mean <= {self.floor}"
        return None


@dataclass(frozen=True)
class TrailingWinrateCriterion:
    window: int = 20
    floor: float = 0.45
    name: str = "trailing_winrate"

    def evaluate(self, r: np.ndarray) -> str | None:
        if r.size >= self.window and (r[-self.window:] > 0).mean() < self.floor:
            return f"trailing-{self.window} win% < {self.floor*100:.0f}"
        return None


@dataclass(frozen=True)
class SignificanceCriterion:
    """Realized mean more than n_se standard errors below the prior."""
    prior_per_trade: float
    n_se: float = 2.0
    min_trades: int = 20
    name: str = "significance"

    def evaluate(self, r: np.ndarray) -> str | None:
        if r.size >= self.min_trades:
            se = r.std() / np.sqrt(r.size)
            if r.mean() < self.prior_per_trade - self.n_se * se:
                return f"realized mean > {self.n_se:.0f} SE below prior"
        return None


CRITERIA = {
    "drawdown": DrawdownCriterion,
    "trailing_mean": TrailingMeanCriterion,
    "trailing_winrate": TrailingWinrateCriterion,
    "significance": SignificanceCriterion,
}


class KillSwitch:
    def __init__(self, criteria):
        self.criteria = list(criteria)

    def check(self, net_rets) -> str | None:
        """First tripped criterion's reason, or None. Empty history = no trip."""
        r = np.asarray(list(net_rets), dtype=float)
        if r.size == 0:
            return None
        for c in self.criteria:
            if (reason := c.evaluate(r)):
                return reason
        return None


def build_killswitch(manifest: Manifest) -> KillSwitch:
    """Instantiate a strategy's pre-registered kill criteria from its manifest."""
    return KillSwitch(CRITERIA[k.kind](**k.params) for k in manifest.kill_criteria)
