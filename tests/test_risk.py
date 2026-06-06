"""core.live.risk — the generalized kill-switch must reproduce
pead_core.kill_check behavior exactly when built from PEAD's manifest
(the criteria arithmetic was ported verbatim; these tests pin it).
"""
import numpy as np

from core.live.risk import KillSwitch, build_killswitch
from strategies.pead.manifest import MANIFEST


def _ks() -> KillSwitch:
    return build_killswitch(MANIFEST)


def test_none_when_empty_or_healthy():
    ks = _ks()
    assert ks.check([]) is None
    assert ks.check([0.01, 0.02, 0.01]) is None
    assert ks.check([0.01] * 25) is None


def test_drawdown_trips():
    assert "drawdown" in _ks().check([0.05, -0.15])


def test_trailing_mean_trips():
    assert "mean" in _ks().check([-0.001] * 20)


def test_winrate_trips():
    r = [0.05] * 8 + [-0.001] * 12   # mean>0 but 40% win
    assert "win%" in _ks().check(r)


def test_significance_trips():
    # 25 trades, tight distribution well below the +1% prior, no other trips
    rng = np.random.default_rng(7)
    r = rng.normal(0.001, 0.0005, 25)          # mean ~0.1%, prior 1%
    r = np.clip(r, 0.0001, None)               # all positive: win% fine, dd fine
    assert "SE below prior" in _ks().check(r)


def test_criteria_order_first_trip_wins():
    # both drawdown and trailing-mean would trip; drawdown is declared first
    r = [-0.01] * 20
    assert "drawdown" in _ks().check(r)
