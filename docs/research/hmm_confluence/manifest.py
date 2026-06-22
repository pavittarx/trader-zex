"""HMM-confluence — the original regime × structure strategy."""
from core.manifest import Manifest, Stage

MANIFEST = Manifest(
    name="hmm_confluence",
    stage=Stage.backtest,   # archived backtest reference; not discovered by runners
    broker="fyers",
    strategy_path="docs.research.hmm_confluence.strategy:HMMConfluenceStrategy",
    config_path="docs.research.hmm_confluence.strategy:HMMConfluenceConfig",
    params=dict(),  # reads BACKTEST_*/HMM_*/STRUCTURE_* from core config
    notes="15m entries gated by 60m regime; sweep verdict: not tradable as-is",
)
