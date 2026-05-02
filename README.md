# trader-zex

A multi-symbol, multi-timeframe market regime screener for Indian equities, powered by a Hidden Markov Model (HMM). It connects to the Fyers API v3 to fetch OHLCV data, classifies each bar as **Bullish**, **Sideways**, or **Bearish**, detects structural price levels (support/resistance), and produces a confluence signal table.

## How it works

1. **HMM Regime Detection** — A 3-state Gaussian HMM is fit on two features per bar: log return and range ratio (intrabar volatility proxy). States are ranked by a composite score (`mean_return − mean_volatility`) and labelled Bullish / Sideways / Bearish.

2. **Structure Detection** — Support and resistance levels are identified using either:
   - `atr` (default): Keltner-style ATR bands around an EMA
   - `pivot`: Scipy-based swing high/low detection

3. **Confluence Signals** — Regime + price location are combined into a signal per (symbol × timeframe): `★ STRONG BUY/SELL`, `↑ WEAK BUY`, `⊙ TAKE PROFIT`, `◎ WATCH`, `· NEUTRAL`, `⏸ WAIT`, `✕ AVOID`.

4. **Efficient API batching** — Instead of one API call per (symbol × timeframe), the screener makes at most 2 calls per symbol: one 1-min fetch resampled to all requested intraday timeframes, and one daily fetch for D/W/M timeframes.

## Setup

**Prerequisites:** Python 3.12+, [uv](https://github.com/astral-sh/uv), a [Fyers](https://fyers.in) trading account with API v3 credentials.

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
uv run python auth.py
```

## Usage

```bash
# Screen default symbols across default timeframes (5, 15, 60, D)
uv run python main.py

# Screen specific symbols
uv run python main.py --symbols NSE:RELIANCE-EQ NSE:TCS-EQ --timeframes 15 60 D

# Screen the full Nifty 500 tradable universe (filtered by price/volume, cached daily)
uv run python main.py --universe

# Launch the Reflex web dashboard
uv run reflex run
```

Or via `poe` task shortcuts:

```bash
uv run poe screen       # python main.py
uv run poe universe     # python main.py --universe
uv run poe dashboard    # reflex run
uv run poe auth         # python auth.py
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

**Price levels** — support, resistance, and % distance from current price (using the last requested timeframe as reference).

## Configuration

All tunable parameters live in [config.py](config.py):

| Parameter | Default | Description |
|---|---|---|
| `HMM_N_STATES` | `3` | Number of HMM states |
| `HMM_N_ITER` | `1000` | EM iterations |
| `HMM_MIN_SAMPLES` | `100` | Minimum bars required to fit |
| `DEFAULT_SYMBOLS` | Nifty 50 large-caps | Symbols screened by default |
| `DEFAULT_TIMEFRAMES` | `["5","15","60","D"]` | Timeframes screened by default |
| `API_SLEEP_SECONDS` | `0.5` | Delay between API calls |
| `STRUCTURE_METHOD` | `"atr"` | `"atr"` or `"pivot"` |
| `STRUCTURE_ATR_PERIOD` | `14` | ATR lookback |
| `STRUCTURE_EMA_PERIOD` | `20` | EMA period for band midline |
| `STRUCTURE_ATR_MULT` | `2.0` | Band width multiplier |
| `STRUCTURE_PROXIMITY_PCT` | `2.0` | % threshold to classify price as "at" a level |
| `UNIVERSE_MAX_PRICE` | `₹500` | Upper LTP filter for universe mode |
| `UNIVERSE_MIN_VOLUME` | `500,000` | Minimum daily volume filter |

## Project structure

```
trader-zex/
├── main.py           # CLI entry point
├── screener.py       # Multi-symbol multi-timeframe orchestration
├── hmm_model.py      # GaussianHMM regime detection
├── structure.py      # Support/resistance level detection
├── confluence.py     # Signal generation from regime + structure
├── fyers_client.py   # Fyers API v3 wrapper + OHLCV resampling
├── auth.py           # Fyers OAuth2 authentication helpers
├── universe.py       # Nifty 500 tradable universe filter (cached daily)
├── config.py         # All configuration constants
├── dashboard.py      # Reflex dashboard entrypoint
└── trader_zex/       # Reflex app components
```

## Dependencies

- [`fyers-apiv3`](https://pypi.org/project/fyers-apiv3/) — Fyers broker API
- [`hmmlearn`](https://hmmlearn.readthedocs.io/) — Hidden Markov Models
- [`scikit-learn`](https://scikit-learn.org/) — Feature standardisation
- [`scipy`](https://scipy.org/) — Pivot/swing detection
- [`pandas`](https://pandas.pydata.org/) / [`numpy`](https://numpy.org/) — Data processing
- [`nsepython`](https://pypi.org/project/nsepython/) — NSE Nifty 500 universe
- [`reflex`](https://reflex.dev/) — Web dashboard framework
- [`python-dotenv`](https://pypi.org/project/python-dotenv/) — `.env` loading
