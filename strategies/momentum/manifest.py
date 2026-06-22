"""Cross-sectional momentum on Nifty 500.

Pipeline: hypothesis → triage → vectorized → backtest → sandbox → live
"""
from core.manifest import KillCriterion, Manifest, Stage

MANIFEST = Manifest(
    name="momentum",
    stage=Stage.hypothesis,
    broker="fyers",
    # strategy_path="strategies.momentum.strategy:MomentumStrategy",  # once stage >= backtest
    universe=[],  # Nifty 500 — populated from registry
    params={
        "lookback_months": 12,
        "ranking_months": 1,
        "quintile": 1,  # top quintile
        "rebalance_freq": "weekly",
        "turnover_threshold_pct": 1.5,  # only trade if position change > 1.5% of portfolio
        "max_single_position_pct": 5,
    },
    kill_criteria=[
        # Locked before sandbox. Kinds: core.live.risk.CRITERIA
        KillCriterion("drawdown", {"dd_limit": 0.15}),
        KillCriterion("trailing_winrate", {"window": 20, "floor": 0.45}),
    ],
    notes="12-1 month cross-sectional momentum, weekly rebalance, Nifty 500",
)
