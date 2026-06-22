# CLAUDE.md

Guidance for working in this repository.

## What this project is

**Trader Zex** is a multi-strategy trading research pipeline for Indian
equities (NSE, via Fyers) with a broker-agnostic core. Strategies move through
a stage-gated lifecycle (see `docs/PIPELINE.md`):

```
hypothesis → triage → vectorized → backtest → sandbox → live
     └──────────┴─────────┴────────────┴──────────┴──→ dropped (any time)
```

Each strategy is a self-contained folder under `strategies/<name>/` with a
machine-readable `manifest.py` (stage, params, universe, kill criteria,
broker) and a human `STATUS.md` (hypothesis, findings, stage history, kill
log). Runners enforce the stage gates.

## Layout

| Path | Responsibility |
|------|---------------|
| `core/config.py` | Infra config only (creds, token path, rate limits, `HMM_*`, `STRUCTURE_*`, `BACKTEST_*` engine defaults, `UNIVERSE_*`) |
| `core/manifest.py` | `Stage` / `Manifest` / `KillCriterion` — the lifecycle contract |
| `core/brokers/` | `base.py` DataAdapter+ExecutionAdapter ABCs + registry; `fyers/` (client, TOTP auth, adapter). Strategies NEVER import a broker — the manifest names one, the runner injects it |
| `core/signals/` | hmm_model (3-state Gaussian HMM regime), structure (S/R via ATR Keltner/pivots), confluence (3×3 regime×location → signal) |
| `core/research/` | Vectorized harness: `data` (chunked fetch + parquet cache), `cost`, `stats` (sharpe/t/IC/DD), `event_study` (reaction/drift/IC — strategy-agnostic), `events_nse` (earnings dates), `report` |
| `core/backtest/` | NautilusTrader glue: data_loader (IST→UTC), instruments, signal_precompute (no look-ahead, disk-cached), engine, metrics |
| `core/live/` | `risk.py` (KillSwitch criteria registry), `state.py` (persisted halt state `~/.trader_zex/state/`), `monitor.py` (offline kill-check CLI) |
| `core/operators/` | Operator tools consuming core: screener, ranker, universe, main (screener CLI). NOT importable by strategies |
| `strategies/<name>/` | manifest.py, STATUS.md, core.py (signal/risk logic), strategy.py (the ONE NT Strategy: backtest = live), backtest.py (runner entry), research/, tests/ |
| `runners/` | `list`, `backtest`, `sandbox`, `live` — stage-gated entry points |
| `scripts/` | Generic research CLIs only (feature_ic, intraday_edge, ranker_ic, screener_data) |
| `trader_zex/` + `rxconfig.py` | Reflex web dashboard |

Current strategies: **pead** (stage: sandbox — see its STATUS.md milestones),
**momentum** (stage: backtest). New strategy: copy `strategies/_template/`.

## Commands

This project uses **`uv`** and **poe** tasks (see `pyproject.toml`).

```bash
uv run python -m runners.list                  # all strategies + stages + halt status
uv run python -m runners.backtest pead         # stage >= backtest enforced
uv run python -m runners.backtest momentum --all-symbols
uv run python -m runners.sandbox pead          # stage >= sandbox + not halted
uv run python -m runners.live pead --i-am-sure # stage == live EXACTLY
uv run python -m core.live.monitor pead [--csv trades.csv | --reset-halt]

uv run poe screen        # screener (core/operators/main.py)
uv run poe rank          # daily ranked stocks (core/operators/ranker.py)
uv run poe backtest      # legacy HMM portfolio backtest CLI (core/backtest)
uv run poe app           # reflex web dashboard
uv run poe auth          # Fyers OAuth/TOTP bootstrap

uv run pytest            # fast suite; -m slow for HMM-fit tests
```

## Critical conventions (don't regress these)

1. **NautilusTrader version is 1.226** — APIs are version-sensitive. Notably:
   - `engine.trader.analyzer` **does not exist**. Use `generate_positions_report()`.
   - The positions report `realized_pnl` is a **string** like `"2910.00 INR"` —
     parse with `float(str(val).split()[0])`. The *fills* report has no P&L.
   - NT `Logger`: `self.log.info(f"...")` — **single string arg only**, no `%` args.
   - Short selling requires `AccountType.MARGIN` (not CASH).
2. **IST→UTC**: subtract 5h30m from IST-naive timestamps, then use
   `Timestamp.value` for nanoseconds. EOD bars open at 09:15 IST → 03:45 UTC.
3. **No look-ahead bias**: signals are computed on expanding windows
   (`bars[:i+1]`) in `signal_precompute.py`. Never feed future bars.
4. **Survivorship bias guard**: `--use-ranker` deliberately prints rankings and
   **exits** — it must NOT select symbols for a historical backtest (today's
   rankings choosing historical winners = look-ahead). Use `--all-symbols` for
   fair backtesting. A faithful ranker backtest needs point-in-time ranking.
5. **Position state** in the strategy is derived from
   `portfolio.is_net_long/is_net_short`, never a manual `_position_side` field
   (that desyncs on order rejection). `on_order_rejected` / `on_position_closed`
   reset manual `_stop_price` / `_trade_count`.
6. **Signal cache key** includes a config hash so HMM/structure param changes
   invalidate stale cached signals. The research harness's parquet cache keys
   include the adapter's venue.
7. **Manifests are the single source of strategy params.** PEAD's params/
   universe/kill-criteria live ONLY in `strategies/pead/manifest.py` — never
   re-add them to `core/config.py`. Kill criteria are pre-registered: locked
   before sandbox, evaluated mechanically (`core.live.risk`), no overrides.
8. **One NT Strategy class per strategy** — the class that backtests is the
   class that trades. No parallel cron reimplementation (removed once; drifts).
9. **Stage gates are enforced, not advisory.** `stage` lives in the manifest;
   changing it is a promotion/demotion decision recorded in STATUS.md.
10. **Brokers are injected.** Strategy code must not import `core.brokers.fyers`
    directly; declare `broker=` in the manifest and let runners inject the
    `DataAdapter` (`runners._common.broker_for`).

## Environment notes

- Requires Fyers API credentials in `.env` and a token at `~/.fyers_token.json`
  (created by `core/brokers/fyers/auth.py`; headless TOTP refresh available via
  `FYERS_FY_ID`/`FYERS_PIN`/`FYERS_TOTP_SECRET`).
- Python deps are **not** on the bare interpreter — always run via `uv run`.
- The sandbox/live TradingNode (Fyers NT data/exec clients) is **not built
  yet** — see milestones in `strategies/pead/STATUS.md`. Sandbox runs need EC2
  in market hours; offline kill-switch machinery is in `core/live/`.
