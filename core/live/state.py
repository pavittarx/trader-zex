"""Persisted per-strategy run state — survives process restarts.

ENVIRONMENTS.md: a tripped kill-switch is a HARD halt; the runner must
refuse to restart a halted strategy until the halt is explicitly reset
(which is a human decision recorded in STATUS.md).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

_STATE_DIR = Path("~/.trader_zex/state").expanduser()


@dataclass
class StrategyState:
    name: str
    halted: bool = False
    halted_reason: str | None = None
    halted_at: str | None = None
    # chronological realized trades: {"date", "symbol", "net_ret"}
    realized: list[dict] = field(default_factory=list)

    @property
    def net_returns(self) -> list[float]:
        return [t["net_ret"] for t in self.realized]

    def record_trade(self, date: str, symbol: str, net_ret: float) -> None:
        self.realized.append({"date": date, "symbol": symbol, "net_ret": float(net_ret)})

    def halt(self, reason: str) -> None:
        self.halted = True
        self.halted_reason = reason
        self.halted_at = datetime.now(timezone.utc).isoformat()

    def reset_halt(self) -> None:
        self.halted = False
        self.halted_reason = None
        self.halted_at = None


def _path(name: str) -> Path:
    return _STATE_DIR / f"{name}.json"


def load(name: str) -> StrategyState:
    p = _path(name)
    if not p.exists():
        return StrategyState(name=name)
    return StrategyState(**json.loads(p.read_text()))


def save(state: StrategyState) -> None:
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    _path(state.name).write_text(json.dumps(state.__dict__, indent=2))
