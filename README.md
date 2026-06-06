# trader-zex

An Indian-equity (NSE) regime screener, daily stock ranker, and event-driven
backtesting system, powered by a Hidden Markov Model (HMM). It connects to the
Fyers API v3 for OHLCV data, classifies market regime as **Bullish**,
**Sideways**, or **Bearish**, locates price relative to support/resistance, and
combines the two into actionable signals.

```
Fyers OHLCV  →  HMM regime  ┐
                            ├─ confluence signal ─┐
structure (S/R levels) ─────┘                     ├─ ranker (daily top-N picks)
                                                  └─ backtest strategy (15m + 60m)
```

## How it works

1. **HMM Regime Detection** (`core/hmm_model.py`) — A 3-state Gaussian HMM is fit
   on two features per bar: log return and range ratio (intrabar volatility
   proxy). States are ranked by a composite score (`mean_return − mean_volatility`)
   and labelled Bullish / Sideways / Bearish.

2. **Structure Detection** (`core/structure.py`) — Support and resistance levels
   are identified using either:
   - `atr` (default): Keltner-style ATR bands around an EMA
   - `pivot`: Scipy-based swing high/low detection

3. **Confluence Signals** (`core/confluence.py`) — Regime + price location are
   combined via a 3×3 matrix into a signal per (symbol × timeframe):
   `★ STRONG BUY/SELL`, `↑ WEAK BUY`, `⊙ TAKE PROFIT`, `◎ WATCH`, `· NEUTRAL`,
   `⏸ WAIT`, `✕ AVOID`.

4. **Consumers** — the signal stack feeds three front-ends:
   - **Screener** (`core/screener.py` + `core/main.py`) — regime/signal/levels
     tables across symbols and timeframes, with efficient API batching (at most
     2 calls per symbol: one 1-min fetch resampled to all intraday timeframes,
     one daily fetch for D/W/M).
   - **Ranker** (`core/ranker.py`) — daily multi-factor composite score over the
     universe → top-N long/short candidates.
   - **Backtester** (`backtest/`) — NautilusTrader event-driven backtest of the
     entry/exit rules.

## The ranker

`StockRanker.rank()` scores each symbol (weights in `core/config.py`):

| Weight | Factor |
|---|---|
| 40% | Confluence signal strength on 15-min bars |
| 30% | Structure proximity — closeness to support (long) / resistance (short) |
| 20% | Momentum — recent return, direction-adjusted |
| 10% | Volume surge vs. 20-day average, capped |

Direction is set by the **60-min regime** (Bullish→LONG, Bearish→SHORT,
Sideways→LONG at reduced score). Results cache to `~/.trader_zex_rankings.json`
per calendar day.

## The backtester

NautilusTrader-based event-driven engine (`backtest/`):

- **Signals are precomputed per bar on expanding windows** — no look-ahead bias
  (`signal_precompute.py`, disk-cached keyed by a config hash).
- **Strategy**: 15-min entries filtered by the 60-min regime; exits on
  take-profit signal, regime flip, stop-loss, or EOD flatten (15:15 IST).
  Fixed-fractional sizing (`BACKTEST_RISK_PCT` of equity per trade).
- **Realistic costs**: per-leg commission including STT on sells.
- **Survivorship-bias guard**: `--use-ranker` prints today's rankings then
  exits — today's picks must not select symbols for a historical backtest.
  Use `--all-symbols` for a fair run.

## Setup

**Prerequisites:** Python 3.12+, [uv](https://github.com/astral-sh/uv), a
[Fyers](https://fyers.in) trading account with API v3 credentials.

```bash
git clone <repo-url>
cd trader-zex
uv sync
```

Create a `.env` file in the project root:

```env
FYERS_CLIENT_ID=YOUR_CLIENT_ID-100
FYERS_SECRET_KEY=YOUR_SECRET_KEY
FYERS_REDIRECT_URI=https://trade.fyers.in/api-login/redirect-uri/index.html
```

Authenticate (once per day — token is cached in `~/.fyers_token.json`):

```bash
uv run poe auth
```

## Usage

All entry points are `poe` tasks (see `pyproject.toml`):

```bash
uv run poe screen       # screener on default symbols      (python -m core.main)
uv run poe universe     # screen the full Nifty 500        (python -m core.main --universe)
uv run poe rank         # today's ranked top-N candidates  (python -m core.ranker)
uv run poe backtest     # run the backtester               (python -m backtest)
uv run poe app          # Reflex web dashboard             (reflex run)
uv run poe auth         # Fyers OAuth bootstrap            (python -m core.auth)
```

Screener options:

```bash
uv run python -m core.main --symbols NSE:RELIANCE-EQ NSE:TCS-EQ --timeframes 15 60 D
```

Backtest CLI:

```bash
uv run python -m backtest                      # DEFAULT_SYMBOLS
uv run python -m backtest --all-symbols        # full fixed universe (fair)
uv run python -m backtest --symbols NSE:RELIANCE-EQ NSE:TCS-EQ
uv run python -m backtest --allow-shorts       # enable short side
uv run python -m backtest --date-from 2024-01-01 --date-to 2024-06-30
uv run python -m backtest --use-ranker         # print rankings, then EXIT
```

Tests:

```bash
uv run pytest            # fast suite (slow HMM-fit tests deselected by default)
uv run pytest -m slow    # the slow ones
```

## Output

**Regime table** — current HMM regime per symbol per timeframe:
```
▲ Bullish  |  — Sideways  |  ▼ Bearish  |  ✕ Error
```

**Confluence signals** — combined regime + structure signal:
```
★ STRONG BUY/SELL  |  ↑ WEAK BUY  |  ⊙ TAKE PROFIT
◎ WATCH  |  · NEUTRAL  |  ⏸ WAIT  |  ✕ AVOID
```

**Price levels** — support, resistance, and % distance from current price
(using the last requested timeframe as reference).

## Configuration

All tunable parameters live in [core/config.py](core/config.py), grouped by
prefix: `HMM_*`, `STRUCTURE_*`, `UNIVERSE_*`, `RANKER_*`, `BACKTEST_*`.
Highlights:

| Parameter | Default | Description |
|---|---|---|
| `HMM_N_STATES` | `3` | Number of HMM states |
| `HMM_MIN_SAMPLES` | `100` | Minimum bars required to fit |
| `STRUCTURE_METHOD` | `"atr"` | `"atr"` or `"pivot"` |
| `STRUCTURE_PROXIMITY_PCT` | `2.0` | % threshold to classify price as "at" a level |
| `UNIVERSE_MAX_PRICE` | `₹5000` | Upper LTP filter for universe mode |
| `UNIVERSE_MIN_VOLUME` | `500,000` | Minimum daily volume filter |
| `RANKER_TOP_N` | `25` | Top-N long and short candidates |
| `BACKTEST_RISK_PCT` | `0.02` | Equity fraction risked per trade |
| `BACKTEST_COMMISSION_BUY/SELL` | `12 / 37 bps` | Per-leg costs incl. STT on sells |

## Project structure

```
trader-zex/
├── core/                  # Core pipeline package
│   ├── main.py            # CLI entry point (screener)
│   ├── screener.py        # Multi-symbol multi-timeframe orchestration
│   ├── hmm_model.py       # GaussianHMM regime detection
│   ├── structure.py       # Support/resistance level detection
│   ├── confluence.py      # Signal generation from regime + structure
│   ├── ranker.py          # Daily multi-factor stock ranking
│   ├── fyers_client.py    # Fyers API v3 wrapper + OHLCV resampling
│   ├── auth.py            # Fyers OAuth2 authentication helpers
│   ├── universe.py        # Nifty 500 tradable universe filter (cached daily)
│   └── config.py          # All configuration constants
├── backtest/              # NautilusTrader backtesting engine
│   ├── __main__.py        # CLI: python -m backtest
│   ├── data_loader.py     # Fyers DataFrame → NT Bars (IST→UTC)
│   ├── signal_precompute.py # Per-bar rolling signals, no look-ahead
│   ├── instruments.py     # NSE Equity instrument definitions
│   ├── strategy.py        # HMMConfluenceStrategy (15m entry / 60m filter)
│   ├── engine.py          # Single-symbol and portfolio runners
│   └── metrics.py         # Win rate, P&L, drawdown, profit factor
├── scripts/               # One-off research/validation scripts (IC tests, PEAD, gap-fade…)
├── tests/                 # pytest suite
├── docs/                  # Architecture diagram & strategy research docs
│   ├── ARCHITECTURE.md
│   ├── STRATEGY_GUIDELINES.md
│   ├── PEAD_THESIS.md
│   ├── GAP_FADE_THESIS.md
│   ├── RESEARCH_BACKLOG.md
│   └── TASKS.md
└── trader_zex/            # Reflex web app components
```

## Dependencies

- [`fyers-apiv3`](https://pypi.org/project/fyers-apiv3/) — Fyers broker API
- [`hmmlearn`](https://hmmlearn.readthedocs.io/) — Hidden Markov Models
- [`nautilus-trader`](https://nautilustrader.io/) — Event-driven backtesting engine
- [`scikit-learn`](https://scikit-learn.org/) — Feature standardisation
- [`scipy`](https://scipy.org/) — Pivot/swing detection
- [`pandas`](https://pandas.pydata.org/) / [`numpy`](https://numpy.org/) — Data processing
- [`nsepython`](https://pypi.org/project/nsepython/) — NSE Nifty 500 universe
- [`reflex`](https://reflex.dev/) — Web dashboard framework
- [`python-dotenv`](https://pypi.org/project/python-dotenv/) — `.env` loading
