"""strategies — one folder per trading strategy, at every lifecycle stage.

Each folder is self-contained: manifest.py (machine-readable stage, params,
universe, kill criteria, broker), STATUS.md (hypothesis, findings log, stage
history, kill log), core.py (pure signal/risk logic), strategy.py (the one
NautilusTrader Strategy class used by backtest AND sandbox/live), research/
(vectorized tests built on core.research), tests/.

Dropped strategies stay here with stage=dropped — the negative result and
its STATUS.md post-mortem are part of the record. Discovery is by filesystem
convention (runners._common.discover); copy _template/ to start a new one.
"""
