# Environments — Backtest / Sandbox / Live (all NautilusTrader)

**Mandate: every environment runs through NautilusTrader.** One NT `Strategy`
class per strategy (`strategies/<name>/strategy.py`) — the class that backtests
is the class that trades. Across environments **only the NT data client and the
NT execution client change**; the strategy logic, the engine semantics, the fill
model, and the risk path are identical. This is pipeline hard rule #4: *no
parallel cron/batch reimplementation* — it drifts from live and was removed once
already (see [PIPELINE.md](PIPELINE.md)).

## Matrix (target — all NT)
| | Backtest | Sandbox | Live |
|---|---|---|---|
| Entry | `runners.backtest <s>` | `runners.sandbox <s>` | `runners.live <s> --i-am-sure` |
| Stage gate | ≥ `backtest` | ≥ `sandbox` | `== live` (exact) |
| Engine | NT `BacktestEngine` | NT `TradingNode` | NT `TradingNode` |
| Data client | historical bars (`df_to_bars`) | Fyers NT live `DataClient` | Fyers NT live `DataClient` (same) |
| Execution client | engine-simulated | NT `SandboxExecutionClient` (paper fills) | **real Fyers NT `ExecutionClient`** |
| Orders hit broker? | no | no | **YES** |
| Capital | notional | none (book only) | real, tiny (₹5000) |
| Purpose | validate edge on history | forward paper-test on live data vs kill-switch | harvest the edge, small |

Because sandbox and live share the same `TradingNode`, data client, and fill
semantics, a clean sandbox forward-test is a faithful preview of live. That is
the entire point of the NT-everywhere rule: the sandbox numbers are
promotion-grade *because* nothing but the execution client differs.

## Shared components (used by ≥2 envs)
- Per-strategy `strategy.py` (NT Strategy), `core.py`/`signal.py`, `manifest.py`.
- Fyers NT **`DataClient`** — sandbox + live (live daily/intraday bars). *Not built.*
- Fyers NT **`ExecutionClient`** (real orders) — live only. *Not built.*
- `node.py`-style builder that assembles a `TradingNode` for `{sandbox, live}`,
  injecting the broker named in the manifest. *Not built.*
- Kill-switch: `core/live/risk.py` (`build_killswitch`) wired as an NT risk actor
  that evaluates `kill_check` on realized trades and hard-halts; halt state
  persisted via `core/live/state.py`; inspect/reset with `core/live/monitor.py`.
  Runners refuse halted strategies.

## ⚠️ Non-conforming interim (to be deleted)
`runners/paper.py`, each strategy's `paper.py::run_paper_cycle`, and the
hand-rolled session in `core/live/fyers_sandbox.py` (`LiveMarketDataClient`,
a `@dataclass` `SandboxExecutionClient`, `SandboxObserver`) are a **one-shot EOD
batch** — a custom fill simulator and ledger that does **not** go through NT.

This violates the mandate above: it is exactly the parallel reimplementation
pipeline rule #4 forbids. Its fills, timing, and ledger do **not** match what the
live `TradingNode` will do, so:

- **It is NOT promotion-grade.** Numbers from `run_paper_cycle` must not be used
  to satisfy the sandbox→live gate. Only the NT sandbox `TradingNode` produces
  gate-valid forward-test data.
- **Do not schedule it.** No systemd timer / cron should fire `runners.paper` or
  `runners.sandbox` as a batch. The NT node owns trade timing internally.
- It exists only as a throwaway scaffold from before the NT node was built, and
  should be removed once the NT sandbox node lands.

## Promotion gates (never skip a stage)
1. **Backtest** passes in-sample → eligible for sandbox.
2. **Sandbox** (NT node) forward paper ≥ 2–3 months / ≥ 15 events, kill-criteria
   NOT tripped, live metrics consistent with the prior → eligible for live.
3. **Live** starts at 10–20% of intended size; scale only after 3+ months
   consistent. Any kill-criterion trips at any stage → **demote / halt**.

## Live safety rails (non-negotiable — real money)
- **Separate credentials + Fyers account** for live vs sandbox; never share a token.
- **Hard pre-trade risk checks** (NT `RiskEngine`): max position notional, max
  gross exposure, max single-order size, **daily loss limit**.
- **Kill-switch = hard halt**, persisted: trips → cancel/stop new orders (open
  positions run to their stop/hold exit).
- **Capital cap** (₹5000) and per-trade cap enforced in code, not by trust.
- **Explicit confirmation flag** (`runners.live <name> --i-am-sure`) + `stage == live`
  exactly — live is never run by accident.
- **Reconciliation on startup**: sync internal state to the broker's actual
  positions (via the exec client's position reports) before acting.
- **Alerting** on every order and any halt (you won't be watching the box).

## Build order (remaining)
1. **TOTP headless auth** (`core/brokers/fyers/auth.py`) — done; unblocks unattended data.
2. **Fyers NT `DataClient`** — the big shared piece for sandbox + live. Untestable
   offline → iterate on EC2 in market hours.
3. **Sandbox `TradingNode`** (`strategies/<name>/sandbox.py` building an NT node
   with the Fyers data client + NT `SandboxExecutionClient`) → run the 2–3 month
   forward test. **Delete the `run_paper_cycle` batch at this point.**
4. **Only after sandbox passes:** Fyers NT real `ExecutionClient` + safety rails +
   `strategies/<name>/live.py` building the live `TradingNode`.
