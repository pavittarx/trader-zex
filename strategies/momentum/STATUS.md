# Cross-sectional Momentum — STATUS

**Stage:** backtest (mirror of `manifest.py:MANIFEST.stage` — keep in sync)  
**Broker:** fyers

## Hypothesis

Nifty 500 constituents exhibit mean reversion on intra-month horizons but momentum on 12-1 month cross-sectional return rank. Top quintile (highest 12-month total returns, excluding past month) experiences continued outperformance driven by factor exposure (quality, low volatility) and retail underweight. The edge persists despite costs (~40–65 bps round-trip after STT + spreads) because turnover filter (only trade if portfolio drift > 1.5%) throttles rebalancing churn. Quarterly rebalance reduces cost drag versus weekly.

## Stage history

| Date | Stage | Evidence / decision |
|------|-------|---------------------|
| 2026-06-23 | hypothesis | Initialized; plan: 12-1 lookback on Nifty 500 constituents, quarterly rebalance with turnover gate. IC target >= 0.03. |
| 2026-06-23 | backtest | Promoted after PIT-aware signal/backtest pipeline, cadence testing, and paper-runner implementation. |

## Findings log

- 2026-06-23: Scaffolding phase 1-2; universe curation + cost model in progress.
- 2026-06-23: Gate 5 verification run on quarterly rebalance (63-day cadence), 48 symbols, 2015-2024:
  - Real Sharpe: 5.38
  - Detrended Sharpe: 0.98
  - Permutation test: beat 27.67% of shuffled strategies (FAILED 95% threshold)
  - DSR probability: 0.999
  - Interpretation: raw returns are strong but cross-sectional selection is not better than random under current universe/cost assumptions.
- 2026-06-23: Added ISIN-keyed point-in-time universe registry (`strategies/momentum/research/universe_registry.py`) and wired `MomentumConfig.universe_nifty500()` to query membership by date from SQLite.
- 2026-06-23: Backtest path updated for PIT-aware signals + VWAP proxy fills (`strategies/momentum/backtest.py`):
  - Configurable cadence (`--rebalance-days`) and fill model (`--fill-model vwap|open`)
  - Correct annualization for non-weekly cadence
  - Quarterly run (2020-2024, 50 symbols, VWAP proxy): Sharpe 1.05, annual return 18.30%, max DD -17.61%
- 2026-06-23: Phase 3 walk-forward cadence test (`strategies/momentum/research/phase3_test.py`) selected quarterly rebalance:
  - Selection score (avg of validate+test Sharpe): weekly 0.4365, monthly 0.8034, quarterly 0.9905
  - OOS (2020+): weekly Sharpe 0.8070, monthly 0.7586, quarterly 0.7451 with highest win rate (82.61%)
  - Manifest updated to `rebalance_freq = \"quarterly\"`
- 2026-06-23: Added Phase 4 paper-trade execution loop:
  - `strategies/momentum/paper.py` simulates quarterly rebalance with VWAP fills and persists paper positions/trades.
  - `runners/paper.py` added for runner-based paper mode (`python -m runners.paper <strategy> ...`), gated at stage >= backtest.
  - Smoke run (`--as-of 2024-06-28`) executed successfully: 8 simulated BUY trades, state persisted, kill-switch not tripped.
- 2026-06-23: Added momentum sandbox entrypoint (`strategies/momentum/sandbox.py`) using shared Fyers sandbox session so it can reuse market/execution I/O with PEAD when promoted to sandbox stage.

## Kill / drop log

*(Will populate as gates are tested)*

## Pre-registered kill criteria (before sandbox)

Locked BEFORE the first sandbox trade; no discretion afterwards.
Declared in `manifest.py:kill_criteria` (enforced by core.live.risk):

1. **Drawdown > 15%** → instant halt
2. **Trailing 20-trade win rate < 45%** → instant halt
