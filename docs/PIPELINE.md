# The Strategy Pipeline

How an idea becomes (or fails to become) deployed capital. Every strategy
lives in `strategies/<name>/` and carries a machine-readable stage in its
`manifest.py`; runners enforce the gates. `STATUS.md` in the same folder is
the human record: hypothesis, findings, stage history, kill log.

```
hypothesis → triage → vectorized → backtest → sandbox → live
     └──────────┴─────────┴────────────┴──────────┴──→ dropped (any time)
```

## Stages and gates

| Stage | What happens | Tooling | Gate to advance |
|-------|--------------|---------|-----------------|
| **hypothesis** | Write the edge: what inefficiency, who's wrong, why it persists. Copy `strategies/_template/`. | STATUS.md | A falsifiable claim + a cheap test design |
| **triage** | IC screen on daily/derived features. Kill fast if ~0. | `core.research.stats.spearman_ic`, `feature_ic` pattern | IC meaningfully ≠ 0 with sensible sign |
| **vectorized** | Cheap pandas tests: event study / timing check / cost gate. **Confirm the return is reachable at a tradable price/time, net of 12–25 bps.** This is where gap-fade died. | `core.research` (data, cost, stats, event_study) | Net-of-cost edge survives a wider universe + sub-period split |
| **backtest** | NautilusTrader BacktestEngine with the strategy's ONE NT Strategy class. No look-ahead, realistic fills/costs. | `core/backtest`, `strategies/<name>/backtest.py`, `python -m runners.backtest <name>` | Net Sharpe/DD acceptable; **kill-criteria locked in manifest BEFORE promotion** |
| **sandbox** | Live data, paper fills (NT SandboxExecutionClient), zero capital. True out-of-sample by construction. | `python -m runners.sandbox <name>` | 2–3 months / ≥15 events, no kill tripped, metrics consistent with prior |
| **live** | Real capital, starting 10–20% of intended size. | `python -m runners.live <name> --i-am-sure` | Scale only after ≥3 months consistent |
| **dropped** | The folder stays. STATUS.md records which gate failed, the numbers, and the re-entry condition (usually "none"). | — | Re-entry = a NEW hypothesis folder with fresh forward validation |

## Hard rules (paid for in losses and dead ends)

1. **Turnover first.** Prioritize hypotheses by turnover, not signal strength.
   Every daily-rebalance L/S we tested had its gross edge eaten by ~28%/yr of
   round-trip cost (`strategies/continuation/STATUS.md` is the canonical
   example: real +20%/yr gross, still a losing strategy).
2. **A daily-bar IC proves nothing tradable.** Run the intraday timing check
   before building anything (`strategies/gap_fade/STATUS.md`).
3. **Kill-criteria are pre-registered.** Locked in `manifest.py` before the
   first sandbox trade; evaluated mechanically by `core.live.risk`; a trip
   halts the strategy (persisted — runners refuse to restart). No overrides,
   no arguing with the rule in the moment.
4. **One Strategy class.** The NT Strategy that backtests is the one that
   trades. No parallel cron reimplementation (removed once already — it
   drifts).
5. **Tweaking a live spec = a new in-sample fit.** It restarts the validation
   clock, as a new hypothesis.
6. **Negative results are kept.** Dropped folders document why — they prevent
   re-testing dead ideas and encode the lessons.

## Mechanics

- **New strategy:** `cp -r strategies/_template strategies/<name>`, edit
  manifest + STATUS, build `research/` tests on `core.research`.
- **Stage changes:** edit `stage=` in manifest.py AND add a row to STATUS.md's
  stage history. Runners enforce: backtest needs ≥ backtest, sandbox ≥ sandbox,
  live == live exactly + `--i-am-sure`, dropped runs nowhere.
- **List everything:** `python -m runners.list`
- **Kill-switch status / reset:** `python -m core.live.monitor <name>
  [--csv trades.csv | --reset-halt]`
- **Brokers:** a strategy declares `broker="fyers"` in its manifest; the
  runner injects the adapter (`core.brokers`). Strategies never import a
  broker — adding a forex broker is a new `core/brokers/<name>/` package,
  zero strategy changes.

## Environment spec

See `docs/ENVIRONMENTS.md` for the backtest/sandbox/live TradingNode
architecture and `docs/STRATEGY_GUIDELINES.md` for backtest-validity
checklists (look-ahead, survivorship, fills, costs).
