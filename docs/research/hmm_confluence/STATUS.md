# HMM-confluence — STATUS

**Stage:** backtest (runnable; promotion to sandbox BLOCKED)
**Broker:** fyers

## Hypothesis

A 3-state Gaussian HMM regime (Bullish/Sideways/Bearish) combined with price
location vs support/resistance produces tradable 15-min entries when filtered
by the 60-min regime.

## Stage history

| Date | Stage | Evidence / decision |
|------|-------|---------------------|
| 2026-04 | backtest | Full NT backtest built (engine, signal precompute, no look-ahead) |
| 2026-06 | backtest | Six-family OHLCV sweep (RESEARCH_BACKLOG.md): HMM-confluence among "none tradable" — promotion blocked |

## Findings log

- The signal stack works as a *screener/ranker* (regime context for candidate
  selection) better than as a standalone entry/exit strategy.
- Sweep conclusion 2026-06: simple-OHLCV signal space on NSE equities is empty
  of retail edge. As a daily/intraday rebalancing strategy, cost dominates.

## Kill / drop log

Not dropped — kept at backtest stage as the reference NT strategy and because
its signal stack (core/signals) powers the screener and ranker apps. Do NOT
promote without a step-change (richer data / execution edge), per the backlog.
