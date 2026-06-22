# trader-zex

A multi-strategy trading research pipeline for Indian equities (NSE, via
Fyers API v3), with a broker-agnostic core. Ideas move through a stage-gated
lifecycle — and are dropped, with documented post-mortems, when they fail a
gate:

```
hypothesis → triage → vectorized → backtest → sandbox → live
     └──────────┴─────────┴────────────┴──────────┴──→ dropped (any time)
```

Every strategy is a self-contained folder under `strategies/<name>/`:
`manifest.py` declares the machine-readable stage, params, locked universe,
pre-registered kill criteria, and broker; `STATUS.md` carries the hypothesis,
findings log, and stage history. Runners enforce the gates — a sandbox-stage
strategy cannot start live, a dropped strategy cannot run anywhere.

See **[docs/PIPELINE.md](docs/PIPELINE.md)** for the full process and
**[docs/ENVIRONMENTS.md](docs/ENVIRONMENTS.md)** for the
backtest/sandbox/live architecture.

## Strategies

| Strategy | One-liner |
|---|---|
| `pead` | 20-day post-earnings drift in low-liquidity NSE names; sparse events; trade small, kill fast |
| `momentum` | 12-1 month cross-sectional momentum on Nifty 500; quarterly rebalance with turnover gate |

**Current stage/source of truth:** `manifest.py` for each strategy.  
Run `uv run python -m runners.list` to see live stage status (avoids README drift).

**Archived:** `hmm_confluence` (backtest reference implementation, signals reused in core/)  
See [docs/research/README.md](docs/research/README.md) for sweep conclusion and lessons.

## Usage

```bash
# List all strategies + stages + halt status
uv run python -m runners.list

# Backtest (stage >= backtest required)
uv run python -m runners.backtest momentum          # all symbols
uv run python -m runners.backtest momentum --all-symbols
uv run python -m runners.backtest pead             # paper trading data

# Paper trade (live data, simulated fills; stage >= backtest required)
export $(cat ~/.env | xargs)  # load secrets from ~/.env
uv run python -m runners.paper momentum --as-of 2024-06-28 --n-symbols 50

# Sandbox (TradingNode paper fills; stage >= sandbox required)
uv run python -m runners.sandbox pead

# Live (real capital; stage == live exactly)
uv run python -m runners.live pead --i-am-sure

# Kill-switch monitor + reconciliation
uv run python -m core.live.monitor momentum         # check halt status
uv run python -m core.live.monitor momentum --csv trades.csv --reset-halt

# Operator tools
uv run poe screen        # multi-symbol multi-timeframe regime screener
uv run poe rank          # daily multi-factor top-N candidates
uv run poe auth          # Fyers OAuth/TOTP bootstrap (headless + interactive)

# Tests
uv run pytest            # fast suite (slow HMM-fit tests deselected)
uv run pytest -m slow    # include HMM-fit tests
```

## Layout

```
trader-zex/
├── core/                    # shared, broker- and strategy-agnostic
│   ├── manifest.py          # Stage / Manifest / KillCriterion lifecycle contract
│   ├── brokers/             # DataAdapter ABC + registry; fyers/ (client, TOTP auth)
│   ├── signals/             # HMM regime, S/R structure, confluence matrix
│   ├── research/            # vectorized harness: data+cache, cost, stats, event_study
│   ├── backtest/            # NautilusTrader glue: loader, instruments, engine, metrics
│   ├── live/                # kill-switch criteria, persisted halt state, monitor
│   └── config.py            # infra config only (creds, rate limits, engine defaults)
├── apps/                    # operator tools: screener, ranker, universe, CLI
├── strategies/              # one folder per strategy
│   ├── _template/           # copy to start a new strategy (manifest + config template)
│   ├── pead/                # post-earnings drift
│   ├── momentum/            # cross-sectional momentum
│   └── ...
├── runners/                 # stage-gated entry points: list, backtest, sandbox, live
├── scripts/                 # generic research CLIs (feature_ic, intraday_edge, screener_data)
├── tests/                   # platform test suite
├── docs/                    # PIPELINE, ENVIRONMENTS, STRATEGY_STRUCTURE, guidelines
└── docs/research/           # archived strategies + lessons (hmm_confluence, sweep verdict)
```

**Key: Each strategy is self-contained** — see `strategies/<name>/`:
- `manifest.py` — contract (stage, broker, universe, params, kill_criteria)
- `config.py` — runtime config (reads env vars; secrets from ~/.env, never in git)
- `.env.example` — template for secrets + strategy-specific settings
- `README.md` — hypothesis, edge, params, failure regimes
- `PLAYBOOK.md` — kill-switch rules, deployment ladder (paper → shadow → live)
- `STATUS.md` — stage history, findings log, kill log (human journal)
- `strategy.py` — NautilusTrader Strategy class (backtest = live codepath)
- `backtest.py` — runner entry point: `uv run python -m strategies.<name>.backtest`

See [docs/STRATEGY_STRUCTURE.md](docs/STRATEGY_STRUCTURE.md) for the canonical reference.

## Process: from idea to capital

1. **Hypothesis:** define edge, failure regimes, falsifiers in `README.md` + `STATUS.md`.
2. **Triage:** run cheap IC/event tests in `research/`; kill weak ideas fast.
3. **Vectorized:** prove no look-ahead/survivorship leakage and net-of-cost viability.
4. **Backtest:** run stage-gated strategy backtests with realistic fills/costs.
5. **Paper:** run `runners.paper` cycles (live/cached data, simulated fills, persisted state).
6. **Sandbox:** run TradingNode sandbox for forward OOS monitoring.
7. **Live:** only after evidence is consistent and kill-criteria are locked.

Runners enforce these gates through `manifest.py:stage`; promotion/demotion must be recorded in `STATUS.md`.

## Canonical strategy structure

Each strategy under `strategies/<name>/` should include:
- `manifest.py` (stage, params, broker, kill criteria — machine contract)
- `config.py` (runtime wiring from manifest + env vars)
- `README.md` (hypothesis, assumptions, process)
- `PLAYBOOK.md` (ops runbook: paper → shadow → live)
- `STATUS.md` (stage history and findings log)
- `strategy.py` + `backtest.py` (single codepath philosophy for backtest/live)
- `research/` and `tests/` for signal validation and regression coverage

## Design rules

- **One NT Strategy class per strategy** — the class that backtests is the
  class that trades live (NautilusTrader BacktestEngine ↔ TradingNode). No parallel cron implementations.
- **Brokers are injected, never imported by strategies** — the manifest names
  a broker (`"fyers"`), the runner resolves it via `core.brokers`. Adding a
  forex broker = one new `core/brokers/<name>/` package, zero strategy edits.
- **Kill criteria are pre-registered and mechanical** — locked in the manifest before the
  first sandbox trade, evaluated by `core.live.risk`, halts persisted; runners refuse to restart a halted strategy. No discretionary overrides.
- **Manifest is single source of truth** — strategy params, universe, kill_criteria live ONLY in
  `strategies/<name>/manifest.py`, shared by backtest, paper, sandbox, and live.
- **config.py is self-contained** — reads from manifest + environment variables; same config
  powers backtest (no secrets), paper, sandbox, live (secrets injected). No code forks.
- **Secrets never in code** — always in `~/.env` on host, or injected by Docker/EC2. Runners
  load `FYERS_*` and strategy-specific env vars at startup.

## Setup

**Prerequisites:** Python 3.12+, [uv](https://github.com/astral-sh/uv), a
[Fyers](https://fyers.in) account with API v3 credentials.

```bash
git clone <repo-url> && cd trader-zex && uv sync
```

**Secrets:** Store in `~/.env` on your host machine (never commit to git).

```bash
# Fyers authentication (shared by all strategies)
FYERS_FY_ID=YOUR_FYERS_ID
FYERS_PIN=YOUR_FYERS_PIN
FYERS_TOTP_SECRET=YOUR_TOTP_SECRET_KEY

# Optional: backtest config
BACKTEST_INITIAL_CAPITAL=100000

# Optional: strategy-specific (e.g. for momentum)
MOMENTUM_PAPER_TRADE_SIZE_PCT=100    # sizing for paper/shadow/live
MOMENTUM_LOG_DIR=~/.trader_zex/logs/momentum/
```

Authenticate once:
```bash
uv run poe auth  # headless (if TOTP secret set) or interactive
```

Token is cached at `~/.fyers_token.json` and auto-refreshed daily by runners.

See [docs/FYERS_AUTH.md](docs/FYERS_AUTH.md) for detailed auth flows, TOTP setup, troubleshooting, and EC2/sandbox automation.

## Docker

One image, one container per strategy. Build on local or EC2, deploy when you're
ready — no CI involved. Secrets live on the host at `~/zex/.<strategy>.env` and
are **never** baked into the image.

```bash
# Build
make docker-build
make docker-push REGISTRY=ghcr.io/<you>   # optional: push to a registry

# Run interactively (test / one-off)
make docker-run   STRATEGY=momentum RUNNER=sandbox
make docker-run   STRATEGY=pead     RUNNER=backtest

# Deploy (detached, auto-restarts on crash/reboot)
make docker-deploy  STRATEGY=momentum RUNNER=sandbox
make docker-logs    STRATEGY=momentum
make docker-stop    STRATEGY=momentum
```

Env file format (`~/zex/.momentum.env`):
```bash
FYERS_CLIENT_ID=...
FYERS_SECRET_KEY=...
FYERS_FY_ID=...
FYERS_PIN=...
FYERS_TOTP_SECRET=...
MOMENTUM_PAPER_TRADE_SIZE_PCT=100
```

## Dependencies

[`nautilus-trader`](https://nautilustrader.io/) (event-driven backtest/live engine, pinned 1.226) ·
[`fyers-apiv3`](https://pypi.org/project/fyers-apiv3/) ·
[`hmmlearn`](https://hmmlearn.readthedocs.io/) ·
[`scikit-learn`](https://scikit-learn.org/) · [`scipy`](https://scipy.org/) ·
[`pandas`](https://pandas.pydata.org/) / [`numpy`](https://numpy.org/) ·
[`nsepython`](https://pypi.org/project/nsepython/) ·
[`pyotp`](https://pypi.org/project/pyotp/) ·
[`python-dotenv`](https://pypi.org/project/python-dotenv/)

## Quick Start: Backtest Momentum Strategy

```bash
# No secrets needed for backtest
uv run python -m strategies.momentum.backtest --date-from 2015-01-01 --date-to 2020-12-31

# Or via runner (stage-gated)
uv run python -m runners.backtest momentum
```

Results logged to backtest output + `~/.trader_zex/logs/momentum/`

## Quick Start: Paper Trade

```bash
# Load secrets
export $(cat ~/.env | xargs)

# Paper trade momentum (live Fyers feed, simulated fills)
uv run python -m runners.sandbox momentum

# Shadow live (10% sizing)
MOMENTUM_PAPER_TRADE_SIZE_PCT=10 uv run python -m runners.sandbox momentum
```

## Documentation

- [docs/FYERS_AUTH.md](docs/FYERS_AUTH.md) — Authentication flows: interactive (dev) + headless TOTP (production/EC2)
- [docs/PIPELINE.md](docs/PIPELINE.md) — Full lifecycle + stage gates
- [docs/STRATEGY_STRUCTURE.md](docs/STRATEGY_STRUCTURE.md) — How to add a new strategy
- [docs/ENVIRONMENTS.md](docs/ENVIRONMENTS.md) — Backtest/sandbox/live architecture
- [docs/STRATEGY_GUIDELINES.md](docs/STRATEGY_GUIDELINES.md) — Research discipline (hypothesis → IC → OOS)
- [docs/PEAD_PLAYBOOK.md](docs/PEAD_PLAYBOOK.md) — Deployment runbook (apply pattern to any strategy)
- [strategies/momentum/README.md](strategies/momentum/README.md) — Momentum hypothesis + params
- [strategies/momentum/PLAYBOOK.md](strategies/momentum/PLAYBOOK.md) — Momentum deployment rules + kill-switch criteria
- [strategies/pead/STATUS.md](strategies/pead/STATUS.md) — PEAD findings log + stage history
