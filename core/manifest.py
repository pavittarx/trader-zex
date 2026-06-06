"""Strategy manifest — the machine-readable lifecycle contract.

Every strategy folder (strategies/<name>/) exports a MANIFEST from its
manifest.py. The manifest declares WHERE the strategy is in the pipeline
(stage), WHAT it trades (universe, params), HOW it dies (kill_criteria),
and WHICH broker feeds it. Runners enforce the stage gates; STATUS.md in
the same folder carries the human narrative (hypothesis, findings, drops).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class Stage(IntEnum):
    """Pipeline stage. Ordinal — runners compare with >=.

    dropped sorts below everything: a dropped strategy passes no gate.
    """
    dropped = 0
    hypothesis = 1
    triage = 2
    vectorized = 3
    backtest = 4
    sandbox = 5
    live = 6


@dataclass(frozen=True)
class KillCriterion:
    """A pre-registered kill rule: kind + parameters.

    kind must name a criterion registered in core.live.risk.CRITERIA
    (drawdown, trailing_mean, trailing_winrate, significance, ...).
    """
    kind: str
    params: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Manifest:
    name: str
    stage: Stage
    broker: str = "fyers"
    # dotted path "package.module:ClassName" — resolved lazily by runners so a
    # manifest stays importable even when heavy deps (NautilusTrader) aren't.
    strategy_path: str | None = None
    config_path: str | None = None
    universe: list[str] = field(default_factory=list)
    params: dict = field(default_factory=dict)
    kill_criteria: list[KillCriterion] = field(default_factory=list)
    notes: str = ""  # one-liner shown in `runners list`

    def resolve(self, path: str | None = None):
        """Import and return the object behind strategy_path/config_path."""
        target = path or self.strategy_path
        if not target:
            raise ValueError(f"{self.name}: no path to resolve")
        module_name, _, attr = target.partition(":")
        import importlib
        return getattr(importlib.import_module(module_name), attr)
