"""Template manifest — copy this folder to strategies/<name>/ and edit.

Pipeline: hypothesis → triage → vectorized → backtest → sandbox → live
(or → dropped at any point, with the post-mortem in STATUS.md).
"""
from core.manifest import KillCriterion, Manifest, Stage

MANIFEST = Manifest(
    name="_template",
    stage=Stage.hypothesis,
    broker="fyers",
    # strategy_path="strategies.<name>.strategy:MyStrategy",  # once stage >= backtest
    universe=[],
    params=dict(),
    kill_criteria=[
        # Locked before sandbox. Kinds: core.live.risk.CRITERIA
        # KillCriterion("drawdown", {"dd_limit": 0.08}),
        # KillCriterion("trailing_mean", {"window": 20}),
        # KillCriterion("trailing_winrate", {"window": 20, "floor": 0.45}),
        # KillCriterion("significance", {"prior_per_trade": 0.01}),
    ],
    notes="copy me",
)
