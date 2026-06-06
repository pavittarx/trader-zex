# PEAD (post-earnings announcement drift) — STATUS

**Stage:** sandbox (eligible — forward paper run not yet started)
**Broker:** fyers

## Hypothesis

Investors underreact to earnings news in liquid-but-not-blue-chip NSE names
(median daily traded value ~₹100–300 cr). The reaction-day move continues
(drifts) over the following ~20 sessions. Institutional flow is slow into the
segment; retail dominates the first print. Sparse (~4 events/yr/stock), so
round-trip cost is amortized over a 20-day move rather than a daily rebalance.

## Stage history

| Date | Stage | Evidence / decision |
|------|-------|---------------------|
| 2026-06-01 | vectorized | Pooled IC(reaction, drift_20) positive; sign L/S t-stat significant |
| 2026-06-03 | backtest | Portfolio backtest Sharpe ~1.1, shallow DD — but capacity test diluted to ~0.5 on broader universe |
| 2026-06-05 | backtest | Liquidity-segmented: edge concentrates in low-liq tercile, Sharpe ~1.3 in-sample; NT strategy built (backtest/live parity) |
| 2026-06-06 | sandbox | Promoted: spec + kill-criteria locked (PEAD_PLAYBOOK.md); awaiting sandbox infra |

## Findings log

- Sharpe ~1.1 on the initial portfolio; dilutes to ~0.5 on the broader universe
  → capacity-limited, traded only in the locked low-liq list.
- Fundamental-surprise variant (EPS-based) is NEGATIVE — the price reaction,
  not the accounting surprise, carries the signal (PEAD_THESIS.md).
- In-sample = one ~2yr regime. NOT cross-regime validated. The forward sandbox
  run IS the out-of-sample test.

## Kill / drop log

(none — pre-registered criteria in `manifest.py`, enforced by core.live.risk)

## Milestones to live (docs/ENVIRONMENTS.md gates)

1. **[next] TOTP auth workflow:** the headless login *code* is done
   (`core/brokers/fyers/auth.py`), but the workflow isn't: (a) enable external
   TOTP on the Fyers account + capture the base32 secret into `.env`
   (`FYERS_FY_ID`/`FYERS_PIN`/`FYERS_TOTP_SECRET`), (b) verify `poe auth`
   mints a token with no prompt, (c) daily ~08:45 IST refresh cron with
   failure alerting. Hard dependency for everything below.
2. **Sandbox infra (7b):** Fyers NT `LiveMarketDataClient` (poll daily
   bars) + `SandboxExecutionClient` TradingNode. Untestable offline — build +
   iterate on EC2 in market hours.
3. **Sandbox gate:** 2–3 months / ≥ 15 events, no kill-criterion fired, metrics
   consistent with the prior (net ~+1–2%/trade, win ~52–55%).
4. **Live infra (7c):** real Fyers `ExecutionClient` + pre-trade risk checks +
   reconciliation. Start at 10–20% size; scale after ≥ 3 months consistent.
