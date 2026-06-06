# CLAUDE.md

Guidance for working in this repository.

## What this project is

**Trader Zex** is an Indian-equity (NSE) regime screener, daily stock ranker, and
event-driven backtesting system. The pipeline is:

```
Fyers OHLCV  →  HMM regime  ┐
                            ├─ confluence signal ─┐
structure (S/R levels) ─────┘                     ├─ ranker (daily top-N picks)
                                                  └─ backtest strategy (15m + 60m)
```

The core thesis: classify market regime with a Hidden Markov Model, locate price
relative to support/resistance, combine the two into an actionable signal, then
either rank the universe for live candidate selection or backtest the entry/exit
rules.

## Module map

| File | Responsibility |
|------|---------------|
| `core/hmm_model.py` | Gaussian HMM (hmmlearn) → Bullish / Sideways / Bearish regime from log-return + range-ratio features |
| `core/structure.py` | Support/resistance via ATR Keltner bands (default) or scipy swing pivots |
| `core/confluence.py` | 3×3 matrix mapping (regime × price-location) → signal (STRONG BUY … STRONG SELL) |
| `core/fyers_client.py` | Fyers API v3 OHLCV history, auto token refresh, 1-min base resampling (`RESAMPLE_RULES`, `resample_ohlcv`) |
| `core/universe.py` | Tradable universe (Nifty 500), daily-cached (`get_tradable_universe`) |
| `core/screener.py` | Runs the regime+structure+confluence stack across symbols/timeframes |
| `core/ranker.py` | Daily multi-factor stock ranking → top-N long/short candidates |
| `core/main.py` | CLI screener entry point |
| `rxconfig.py` / `trader_zex/` | Reflex web dashboard |
| `core/auth.py` | Fyers OAuth token bootstrap |
| `backtest/` | NautilusTrader backtesting engine (see below) |

## The ranker (`core/ranker.py`)

`StockRanker.rank(force=False)` returns `RankResult(long, short, scores_df)`.
Composite score (weights in `core/config.py`):

- **40%** signal strength — confluence signal on 15-min bars
- **30%** structure proximity — closeness to support (long) / resistance (short)
- **20%** momentum — 5-day return, direction-adjusted
- **10%** volume surge — recent vs. 20-day average, capped

Direction is set by the **60-min regime** (Bullish→LONG, Bearish→SHORT,
Sideways→LONG with lower score). Results cache to `~/.trader_zex_rankings.json`,
keyed by calendar date; same-day reruns hit the cache unless `force=True`.

## The backtest (`backtest/`)

| File | Responsibility |
|------|---------------|
| `data_loader.py` | Fyers DataFrame → NautilusTrader `Bar` objects; **IST→UTC** conversion |
| `signal_precompute.py` | Rolling per-bar HMM+confluence signals, **no look-ahead**; disk-cached |
| `instruments.py` | NSE `Equity` instrument definitions (with commission fees) |
| `strategy.py` | `HMMConfluenceStrategy` — 15-min entry/exit filtered by 60-min regime |
| `engine.py` | `run_backtest` (single) and `run_backtest_portfolio` (shared capital) |
| `metrics.py` | Win rate, P&L, drawdown, profit factor from the positions report |
| `__main__.py` | CLI: `python -m backtest` |

### Strategy rules (`HMMConfluenceStrategy`)

- **Long entry**: 60-min regime Bullish AND 15-min signal ∈ {STRONG BUY, WEAK BUY}
  AND regime stable (last N signals agree) AND no position.
- **Short entry**: same with Bearish / {STRONG SELL, AVOID}, gated on `allow_shorts`.
- **Exits**: take-profit signal / regime flip / stop-loss / EOD flatten (15:15 IST).
- **Sizing**: fixed-fractional — risk `BACKTEST_RISK_PCT` of equity per trade.

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
   fair backtesting. A faithful ranker backtest needs point-in-time (walk-forward)
   ranking, which is not yet built.
5. **Position state** in the strategy is derived from
   `portfolio.is_net_long/is_net_short`, never a manual `_position_side` field
   (that desyncs on order rejection). `on_order_rejected` / `on_position_closed`
   reset manual `_stop_price` / `_trade_count`.
6. **Signal cache key** includes a config hash so HMM/structure param changes
   invalidate stale cached signals.

## Commands

This project uses **`uv`** and **poe** tasks (see `pyproject.toml`).

```bash
uv run poe screen        # run the screener (core/main.py)
uv run poe rank          # print today's ranked stocks
uv run poe backtest      # run the backtester
uv run poe app           # reflex web dashboard
uv run poe auth          # Fyers OAuth bootstrap

# Backtest CLI
uv run python -m backtest                      # DEFAULT_SYMBOLS
uv run python -m backtest --all-symbols        # full fixed universe (fair)
uv run python -m backtest --symbols NSE:RELIANCE-EQ NSE:TCS-EQ
uv run python -m backtest --use-ranker         # print rankings, then EXIT
uv run python -m backtest --allow-shorts       # enable short side
uv run python -m backtest --date-from 2024-01-01 --date-to 2024-06-30
```

## Environment notes

- Requires Fyers API credentials in `.env` and a token at `~/.fyers_token.json`
  (created by `core/auth.py`). Without them, live data fetches won't run.
- Python deps are **not** on the bare interpreter — always run via `uv run`.
- Config lives in `core/config.py`: `RANKER_*`, `BACKTEST_*`, `HMM_*`, `STRUCTURE_*`,
  `ALL_SYMBOLS`, `DEFAULT_SYMBOLS`.
