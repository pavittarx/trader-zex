# Momentum research workspace

This folder contains **analysis-only** scripts for momentum validation.  
Runtime entrypoints stay at strategy root (`backtest.py`, `paper.py`, `sandbox.py`).

## Layout

- `triage.py` — Gate 1 quick signal triage
- `prepare_data.py` — PIT-aware data prep and parquet cache
- `phase3_test.py` — cadence walk-forward comparison
- `verify_gate5.py` — permutation / detrend / DSR checks
- `momentum_ic.py` — IC harness and self-tests
- `universe_registry.py` — point-in-time ISIN universe registry
- `gate4_walkforward.py` — Gate 4 walk-forward analysis
- `gate4_hyperparam_tuning.py` — parameter sweep / stability checks
- `trend_signal.py` — experimental time-series momentum overlay helper

## Rule of thumb

If a script is not part of stage-gated runtime execution, keep it under
`research/` so strategy root remains operationally focused.
