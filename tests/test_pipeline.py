"""Pipeline machinery: manifest discovery, stage gates, broker registry."""
import pytest

from core.manifest import KillCriterion, Manifest, Stage
from runners._common import discover, load_manifest, require_stage


def test_discover_finds_strategies():
    found = discover()
    assert "pead" in found
    assert "hmm_confluence" in found
    assert "gap_fade" in found
    assert "_template" not in found            # underscore folders skipped


def test_stage_ordering():
    assert Stage.dropped < Stage.hypothesis < Stage.triage < Stage.vectorized \
           < Stage.backtest < Stage.sandbox < Stage.live


def test_pead_manifest_contract():
    m = load_manifest("pead")
    assert m.stage == Stage.sandbox
    assert m.broker == "fyers"
    assert len(m.universe) == 12               # locked list — no mid-flight additions
    assert {k.kind for k in m.kill_criteria} == {
        "drawdown", "trailing_mean", "trailing_winrate", "significance"}


def test_gate_allows_equal_and_above():
    m = load_manifest("pead")                  # stage=sandbox
    require_stage(m, Stage.backtest)           # >= passes
    require_stage(m, Stage.sandbox)


def test_gate_blocks_below():
    m = load_manifest("pead")                  # sandbox < live
    with pytest.raises(SystemExit):
        require_stage(m, Stage.live)


def test_gate_exact_blocks_sandbox_from_live():
    m = load_manifest("pead")
    with pytest.raises(SystemExit):
        require_stage(m, Stage.live, exact=True)


def test_dropped_blocked_everywhere():
    m = load_manifest("gap_fade")
    with pytest.raises(SystemExit):
        require_stage(m, Stage.hypothesis)


def test_unknown_broker_rejected():
    from core.brokers import get_data_adapter
    with pytest.raises(ValueError):
        get_data_adapter("nope")


def test_manifest_resolve_lazy():
    m = Manifest(name="x", stage=Stage.hypothesis, strategy_path="math:sqrt")
    assert m.resolve()(9) == 3.0
