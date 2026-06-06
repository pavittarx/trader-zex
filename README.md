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

| Strategy | Stage | One-liner |
|---|---|---|
| `pead` | **sandbox** | 20-day post-earnings drift in low-liquidity NSE names; sparse events; trade small, kill fast |
| `hmm_confluence` | backtest | HMM regime × S/R structure signals; promotion blocked (OHLCV-sweep verdict) |
| `gap_fade` | dropped | Daily IC was a mirage at realistic entry; cost-killed |
| `continuation` | dropped | Real +20%/yr gross edge, eaten by turnover cost; limit-entry rescue exhausted |
| `reversal` | dropped | Lead weakened out-of-sample (mirage) |
| `breakout` | dropped | NR7 breakout premise wrong — gross ~ 0 |

The dropped folders are kept on purpose: the negative results and their
lessons (turnover-first prioritization, intraday-timing checks) are encoded
in the pipeline's gates.

## Usage

```bash
uv run python -m runners.list                   # strategies + stages + halt status
uv run python -m runners.backtest pead          # NT backtest (stage >= backtest)
uv run python -m runners.backtest hmm_confluence --all-symbols
uv run python -m runners.sandbox pead           # paper trading (stage >= sandbox)
uv run python -m runners.live pead --i-am-sure  # real capital (stage == live exactly)
uv run python -m core.live.monitor pead         # kill-switch status / --reset-halt

# Operator apps
uv run poe screen        # multi-symbol multi-timeframe regime screener
uv run poe rank          # daily multi-factor top-N candidates
uv run poe app           # Reflex web dashboard
uv run poe auth          # Fyers OAuth/TOTP bootstrap

# Tests
uv run pytest            # fast suite (slow HMM-fit tests deselected)
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
│   └── config.py            # infra config only
├── apps/                    # operator tools: screener, ranker, universe, CLI
├── strategies/              # one folder per strategy (see table above)
│   ├── _template/           # copy to start a new strategy
│   └── <name>/              # manifest.py, STATUS.md, core.py, strategy.py,
│                            #   backtest.py, research/, tests/
├── runners/                 # stage-gated entry points (list/backtest/sandbox/live)
├── scripts/                 # generic research CLIs (feature_ic, intraday_edge, …)
├── tests/                   # platform test suite
├── docs/                    # PIPELINE, ENVIRONMENTS, guidelines, theses, playbooks
└── trader_zex/              # Reflex web app
```

## Design rules

- **One NT Strategy class per strategy** — the class that backtests is the
  class that trades live (NautilusTrader BacktestEngine ↔ TradingNode).
- **Brokers are injected, never imported by strategies** — the manifest names
  a broker (`"fyers"`), the runner resolves it via `core.brokers`. Adding a
  forex broker = one new `core/brokers/<name>/` package, zero strategy edits.
- **Kill criteria are pre-registered** — locked in the manifest before the
  first sandbox trade, evaluated mechanically (`core.live.risk`), halts
  persisted; runners refuse to restart a halted strategy. No overrides.
- **Same test, any strategy** — `core/research/event_study.py` runs the
  identical reaction/drift/IC analysis for any event source (PEAD feeds
  earnings dates; the next event strategy feeds its own).

## Setup

**Prerequisites:** Python 3.12+, [uv](https://github.com/astral-sh/uv), a
[Fyers](https://fyers.in) account with API v3 credentials.

```bash
git clone <repo-url> && cd trader-zex && uv sync
```

`.env` in the project root:

```env
FYERS_CLIENT_ID=YOUR_CLIENT_ID-100
FYERS_SECRET_KEY=YOUR_SECRET_KEY
FYERS_REDIRECT_URI=https://trade.fyers.in/api-login/redirect-uri/index.html
# optional — unattended daily token refresh (headless TOTP):
FYERS_FY_ID=...
FYERS_PIN=...
FYERS_TOTP_SECRET=...
```

Authenticate (token cached daily in `~/.fyers_token.json`):

```bash
uv run poe auth
```

## Dependencies

[`nautilus-trader`](https://nautilustrader.io/) (event-driven backtest/live engine, pinned 1.226) ·
[`fyers-apiv3`](https://pypi.org/project/fyers-apiv3/) ·
[`hmmlearn`](https://hmmlearn.readthedocs.io/) ·
[`scikit-learn`](https://scikit-learn.org/) · [`scipy`](https://scipy.org/) ·
[`pandas`](https://pandas.pydata.org/) / [`numpy`](https://numpy.org/) ·
[`nsepython`](https://pypi.org/project/nsepython/) ·
[`pyotp`](https://pypi.org/project/pyotp/) ·
[`reflex`](https://reflex.dev/) ·
[`python-dotenv`](https://pypi.org/project/python-dotenv/)
