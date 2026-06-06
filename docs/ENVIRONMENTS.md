# Three Environments — Backtest / Sandbox / Live

One strategy class (`backtest/pead_strategy.py::PEADStrategy`), one signal/risk
core (`pead_core.py`), one config (`config.PEAD_*`). Across environments **only
the data source and the execution client change** — never the strategy logic.

## Matrix
| | Backtest | Sandbox | Live |
|---|---|---|---|
| Engine | `BacktestEngine` | live `TradingNode` | live `TradingNode` |
| Data | historical bars (`df_to_bars`) | Fyers live adapter (poll daily) | Fyers live adapter (same) |
| Execution | simulated (engine) | `SandboxExecutionClient` | **Fyers `ExecutionClient` (real)** |
| Orders hit broker? | no | no | **YES** |
| Capital | notional | none (book only) | real, tiny (₹5000) |
| Purpose | validate edge on history | forward paper-test vs kill-switch | harvest the edge, small |

## Shared components (build once, used by ≥2 envs)
- `PEADStrategy`, `pead_core`, `config.PEAD_*` — done.
- **Fyers `LiveMarketDataClient`** (data adapter) — sandbox + live. *Not built.*
- Instruments (`backtest/instruments.py`), kill-switch (`pead_core.kill_check`).
- A **risk actor** that evaluates `kill_check` on realized trades and halts.

## Per-environment, differs
- Backtest: `BacktestEngine` + simulated fills. **Done.**
- Sandbox: `TradingNode` + Fyers data adapter + `SandboxExecutionClient`. *Build.*
- Live: `TradingNode` + Fyers data adapter + **Fyers real `ExecutionClient`** +
  the safety rails below. *Build last, only after sandbox passes.*

## Target repo layout
```
core/ (today backtest/)   # BacktestEngine, data_loader, instruments, metrics
strategies/pead/          # pead_strategy.py (+ pead_core.py)
live/
  fyers_data_client.py    # LiveMarketDataClient — SHARED sandbox+live
  fyers_exec_client.py    # ExecutionClient (real orders) — LIVE ONLY
  node.py                 # builds a TradingNode for env in {sandbox, live}
  risk.py                 # kill-switch risk actor (hard halt)
run.py                    # CLI: run --env {backtest|sandbox|live}
config.py                 # ENV selection + SEPARATE creds per env
```

## Promotion gates (never skip a stage)
1. **Backtest** passes in-sample → eligible for sandbox.
2. **Sandbox** forward paper ≥ 2–3 months / ≥ 15 events, kill-criteria NOT
   tripped, live metrics consistent with the prior → eligible for live.
3. **Live** starts at 10–20% of intended size; scale only after 3+ months
   consistent. Any kill-criterion trips at any stage → **demote / halt**.

## Live safety rails (non-negotiable — real money)
- **Separate credentials + Fyers account** for live vs sandbox; never share a token.
- **Hard pre-trade risk checks** (NT `RiskEngine`): max position notional, max
  gross exposure, max single-order size, **daily loss limit**.
- **Kill-switch = hard halt**, persisted: trips → cancel/stop new orders (open
  positions run to their stop/hold exit).
- **Capital cap** (₹5000) and per-trade cap enforced in code, not by trust.
- **Explicit `--env live` + a confirmation flag** so live is never run by accident.
- **Reconciliation on startup**: sync internal state to the broker's actual
  positions (via the exec client's position reports) before acting.
- **Alerting** on every order and any halt (you won't be watching the box).

## Build order
1. **TOTP headless auth** (`auth.py`) — unblocks unattended data for sandbox+live.
2. **Fyers `LiveMarketDataClient`** — enables sandbox (the big shared piece;
   untestable offline → iterate on EC2 in market hours).
3. **Sandbox node + `run --env sandbox`** → run the 2–3 month forward test.
4. **Only after sandbox passes:** Fyers real `ExecutionClient` + safety rails +
   `run --env live` at tiny size.
