# Cross-sectional Momentum — STATUS

**Stage:** hypothesis (mirror of `manifest.py:MANIFEST.stage` — keep in sync)  
**Broker:** fyers

## Hypothesis

Nifty 500 constituents exhibit mean reversion on intra-month horizons but momentum on 12-1 month cross-sectional return rank. Top quintile (highest 12-month total returns, excluding past month) experiences continued outperformance driven by factor exposure (quality, low volatility) and retail underweight. The edge persists despite costs (~40–65 bps round-trip after STT + spreads) because turnover filter (only trade if portfolio drift > 1.5%) throttles rebalancing churn. Weekly rebalance balances signal refresh against execution friction.

## Stage history

| Date | Stage | Evidence / decision |
|------|-------|---------------------|
| 2026-06-23 | hypothesis | Initialized; plan: 12-1 lookback on Nifty 500 constituents, weekly rebalance with turnover gate. IC target >= 0.03. |

## Findings log

- 2026-06-23: Scaffolding phase 1—2; universe curation + cost model in progress.

## Kill / drop log

*(Will populate as gates are tested)*

## Pre-registered kill criteria (before sandbox)

Locked BEFORE the first sandbox trade; no discretion afterwards.
Declared in `manifest.py:kill_criteria` (enforced by core.live.risk):

1. **Drawdown > 15%** → instant halt
2. **Trailing 20-trade win rate < 45%** → instant halt

