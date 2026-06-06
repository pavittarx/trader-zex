"""PEAD (post-earnings announcement drift) — manifest.

The locked spec from docs/PEAD_PLAYBOOK.md. Do NOT tweak params once live;
tweaking = a new in-sample fit and restarts the validation clock.
"""
from core.manifest import KillCriterion, Manifest, Stage

MANIFEST = Manifest(
    name="pead",
    stage=Stage.sandbox,   # backtest passed (Sharpe ~1.3 in-sample); next: sandbox forward run
    broker="fyers",
    strategy_path="strategies.pead.strategy:PEADStrategy",
    config_path="strategies.pead.strategy:PEADStrategyConfig",
    # Locked lower-liquidity universe (the segment where the edge concentrated,
    # PEAD_THESIS.md §9-10). Fixed at launch; no mid-flight additions.
    universe=[
        "NSE:SAIL-EQ", "NSE:NMDC-EQ", "NSE:PNB-EQ", "NSE:CANBK-EQ", "NSE:ASHOKLEY-EQ",
        "NSE:BANKBARODA-EQ", "NSE:HINDPETRO-EQ", "NSE:GAIL-EQ", "NSE:NATIONALUM-EQ",
        "NSE:MOTHERSON-EQ", "NSE:LICHSGFIN-EQ", "NSE:FEDERALBNK-EQ",
    ],
    params=dict(
        hold_bars=20,          # sessions to hold after the reaction
        thresh=0.02,           # min reaction-day |return| to act
        stop_pct=0.12,         # disaster stop (wide — preserve the drift)
        corp_gap=0.25,         # overnight gap above this = probable corporate action
        alloc_pct=0.30,        # equity fraction per position (~3 concurrent)
        max_gross=0.90,        # portfolio gross-exposure cap
        leg_bps=15.0,          # cost per leg (entry, exit), bps
    ),
    # Pre-registered (PEAD_PLAYBOOK.md §kill-criteria). Mechanical, no overrides.
    kill_criteria=[
        KillCriterion("drawdown", {"dd_limit": 0.08}),
        KillCriterion("trailing_mean", {"window": 20}),
        KillCriterion("trailing_winrate", {"window": 20, "floor": 0.45}),
        KillCriterion("significance", {"prior_per_trade": 0.01}),
    ],
    notes="20d drift in low-liq NSE names; sparse events; trade small, kill fast",
)
