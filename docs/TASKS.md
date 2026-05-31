# Trader Zex — Fix Task List

Derived from an adversarial quantitative review of the codebase.
Tasks are ordered by impact: fix the top items first — lower items may
be moot if #1 kills the strategy's edge.

Each task has: **what to change**, **which files**, **what you learn from it**.

---

## Priority 1 — Will make or break the strategy

### T-01 · Model realistic NSE round-trip costs
**Severity: Critical — cost understatement alone may eliminate the entire edge.**

Current state: `config.py:150` sets `BACKTEST_COMMISSION = 0.00065` (13 bps/round-trip).
Honest NSE intraday all-in is ~25–35 bps per round-trip:

| Component | Per leg | Notes |
|-----------|---------|-------|
| STT | 2.5 bps sell-side | Intraday delivery; asymmetric |
| Exchange txn charge | ~0.297 bps/leg | NSE rate |
| SEBI charge | ~0.01 bps/leg | |
| Stamp duty | 0.3 bps buy-side | |
| GST 18% on brokerage+txn | varies | ~0.5 bps effective |
| Bid-ask half-spread | 2–5 bps/leg | Even Nifty 50 large-caps |
| Market-order slippage | 1–3 bps/leg | Scales with size |

**Changes required:**
- `config.py`: raise `BACKTEST_COMMISSION` to `0.0015` (15 bps/leg ≈ 30 bps round-trip)
- `backtest/engine.py` `build_engine()`: replace the trivial `FillModel` with a
  size-aware slippage model. At minimum: `prob_slippage=1.0` (always slips) and
  add an explicit half-spread via a `FixedFeeModel` or post-trade adjustment.
- `backtest/instruments.py`: model STT asymmetry — `maker_fee` (buy leg) ≠ `taker_fee`
  (sell leg). Buy leg ≈ 0.30 bps total charges; sell leg ≈ 0.30 bps + 2.5 bps STT.
- `backtest/metrics.py`: add a `total_cost_inr` column to the summary (sum of
  commissions from the positions report) so cost drag is visible.

**What you learn:** If the strategy isn't profitable at 30 bps round-trip, nothing
else on this list matters. Run this experiment before anything else.

---

### T-02 · Cap position size and portfolio heat
**Severity: Critical — uncapped sizing can produce 2× leverage on a single name.**

Current state: `strategy.py:204-214` sizes as `equity × risk_pct / stop_distance`.
When price is "At Support" (the best `STRONG BUY` entry), stop distance is tiny →
share count explodes. Example: ₹100 price, ₹99.5 support, ₹99.0 stop (0.5% buffer)
→ stop distance ₹1 → shares = 1,000,000 × 0.02 / 1 = 20,000 → ₹20L notional on
a ₹10L account. `AccountType.MARGIN` in `engine.py:62` silently permits this.

There is also no aggregate cap: 30 strategies each risk 2% independently, all going
long in a Bullish regime = one ~40% correlated directional bet on Nifty beta.

**Changes required:**

*Per-position cap* (`backtest/strategy.py`, `_position_size`):
```python
MAX_POSITION_PCT = 0.10   # no single position > 10% of equity
MAX_PARTICIPATION = 0.05  # no more than 5% of bar volume

shares = int((equity * self.config.risk_pct) / stop_distance)

# Hard notional cap
max_by_notional = int(equity * MAX_POSITION_PCT / price)
shares = min(shares, max_by_notional)

# Participation cap (requires bar volume — pass it through on_bar)
max_by_volume = int(bar.volume * MAX_PARTICIPATION)
shares = min(shares, max_by_volume)

return max(shares, 1)
```

*Portfolio heat cap* (`backtest/engine.py` or `backtest/strategy.py`):
- Add a `max_gross_exposure_pct: float = 0.50` config parameter.
- Before submitting a new order, check
  `portfolio.net_exposure(venue) / portfolio.equity(venue) < max_gross_exposure_pct`.
- If at limit, skip the entry.

*Config additions* (`config.py`):
```python
BACKTEST_MAX_POSITION_PCT: float = 0.10
BACKTEST_MAX_PARTICIPATION: float = 0.05
BACKTEST_MAX_GROSS_EXPOSURE: float = 0.50
```

**What you learn:** Whether the historical "profits" were real signal or just
concentrated leverage in bull markets. Expect returns and trade count to drop
significantly, and drawdown to become more realistic.

---

### T-03 · Fix execution timing and intrabar stop checking
**Severity: High — current implementation transacts at unattainable prices.**

Two issues in `backtest/strategy.py`:

**Issue A — one-bar look-ahead in execution.**
`on_bar` reads `bar.close` at line 104, then submits a market order on the *same*
bar at lines 153–156 and 170–175. In live trading, you cannot compute the HMM on
bar *i*'s close and simultaneously fill at bar *i*'s price. The order should fill
at bar *i+1*'s open.

Fix: This is largely a NautilusTrader configuration issue. With `EXTERNAL` bars,
NT fills market orders at the timestamp of the *next* bar received. Verify this
is actually happening by logging `order.filled_qty` and the fill timestamp in
`on_order_filled`. If fills are landing on the same bar's close, add a
one-bar delay by storing the intended order and submitting it at the *next*
`on_bar` call.

**Issue B — stop-loss on bar close underestimates losses.**
`strategy.py:129`: `close <= self._stop_price` — this checks only the *closing*
price of the 15-min bar. A bar can trade well through your stop intrabar and
book the close as the exit price, which is systematically better than reality.

Fix: Also check `float(bar.low) <= self._stop_price` for longs (and
`float(bar.high) >= self._stop_price` for shorts) to detect intrabar stop
touches. Use the stop price as the exit price (not the close) when triggered
intrabar, since that's the realistic fill.

```python
# strategy.py — in on_bar, exit checks
if is_long:
    intrabar_stop_hit = (self._stop_price is not None and
                         float(bar.low) <= self._stop_price)
    close_stop_hit = (self._stop_price is not None and
                      float(bar.close) <= self._stop_price)
    stop_hit = intrabar_stop_hit or close_stop_hit
```

**What you learn:** Expect average loss per trade to worsen. The delta between
current and corrected results tells you exactly how much the current backtest
flatters losing trades.

---

## Priority 2 — Structural model correctness

### T-04 · Measure HMM label stability; replace per-bar refit if unstable
**Severity: High — regime labels may not be consistent bar-to-bar.**

Current state: `signal_precompute.py:94-137` refits a fresh `HMMModel()` on
`df_15m.iloc[:i+1]` for every bar. EM with `random_state=42` does NOT guarantee
stable state assignments as the window grows — it prevents random initialization
jitter within one run, but different window sizes produce different local optima.
The `StandardScaler` re-fit at `hmm_model.py:104` also shifts the feature space
each bar. Result: "Bullish" at bar *i* and bar *i+1* may come from fundamentally
different models.

**Diagnostic experiment (do before changing anything):**
```python
# scripts/check_label_stability.py — new file
# For a symbol with known 90-day history:
# 1. For each bar i from warmup to N:
#    a. fit HMM on bars[:i+1], record current_regime
#    b. fit HMM on bars[:i+2], re-label the same bar i, compare
# 2. Plot: what fraction of time does regime[i] change when we add bar i+1?
# 3. Plot: forward 15-min return conditioned on regime_60m label.
# If >20% of labels flip on window extension → the label is noise.
```

**If labels are unstable, replace the per-bar refit with:**
- A **fixed rolling window** (e.g. last 500 bars, refit every 20 bars) — more
  stable because the distribution changes less between fits.
- Or a **simpler, deterministic trend/vol filter** (e.g. price above/below
  50-bar EMA + ATR-normalized volatility percentile) that is verifiably
  stationary and has no label-switching problem.

**Files:** `hmm_model.py`, `signal_precompute.py`, new `scripts/check_label_stability.py`

**What you learn:** Whether the HMM is adding any information over a naïve
momentum indicator. If it isn't, the simpler filter will perform comparably
with far less compute and no label-switching risk.

---

### T-05 · Validate the confluence matrix with forward-return data
**Severity: Medium — the 3×3 signal table is hand-authored with no empirical backing.**

Current state: `confluence.py:20-30` is a hardcoded lookup table. There is no
evidence that "Bullish + At Support → STRONG BUY" has a higher forward return
than "Bullish + In Middle → WEAK BUY."

Note also an internal inconsistency: `Bullish + At Resistance → TAKE PROFIT`
(`confluence.py:23`) is used as a long *exit* (`strategy.py:130`). But "at
resistance in a bullish regime" is often a *continuation* setup in momentum
frameworks — the strategy systematically sells strength.

**Experiment:**
```python
# scripts/validate_confluence.py — new file
# For each (regime_60m, location) pair in historical data:
# 1. Record the bar's signal.
# 2. Record the forward 15-min and 60-min return.
# 3. Compute mean forward return and t-stat per cell.
# 4. Compare to null (flat return).
# → Do STRONG BUY cells actually have higher forward returns than NEUTRAL?
# → Is TAKE PROFIT actually a reversal point?
```

If the empirical forward returns don't match the hand-authored labels, revise
the table or make the signal a continuous score rather than a categorical lookup.

**Files:** `confluence.py`, new `scripts/validate_confluence.py`

---

### T-06 · Fix the ranker — make factors scale-compatible and direction-aware
**Severity: Medium — two of four factors are strictly non-negative and always add.**

Current state in `ranker.py:302-322`:
- `sig_score ∈ [-1, 1]` — signed, correctly penalizes bad signals
- `mom_score ∈ [-1, 1]` — signed (after direction flip at line 318)
- `prox_score ∈ [0, 1]` — **always non-negative**, never penalizes
- `vol_score ∈ [0, 1]` — **always non-negative**, a selling-climax volume surge
  always *adds* to the score

Also: Sideways-regime stocks are forced into the LONG bucket (`ranker.py:299`)
even when their 15-min signal is `STRONG SELL` — direction and signal can
directly contradict.

**Changes required:**

*Make volume signed:* high volume on a down move should penalize longs.
```python
# ranker.py, in _score()
# Use price_change to sign the volume surge
price_change = (df_daily['close'].iloc[-1] / df_daily['close'].iloc[-2]) - 1
vol_score = min(vol_surge / 3.0, 1.0) * (1 if price_change >= 0 else -1)
# For shorts: invert
if direction == "SHORT":
    vol_score = -vol_score
```

*Make proximity signed:* far from support = bad for a long; far from resistance
= bad for a short. Currently both are 0-if-distant → 1-if-close, symmetric.
That's fine for longs; for shorts invert it.

*Fix Sideways direction:* when `regime_60m == "Sideways"` do not force LONG.
Either skip the symbol entirely, or assign direction based on the 15-min signal.

*Add config parameter:* `RANKER_SIDEWAYS_ACTION: str = "skip"` # or "signal-driven"

**Files:** `ranker.py`, `config.py`

---

### T-07 · Add Nifty benchmark and risk-adjusted metrics
**Severity: Medium — impossible to judge strategy quality without a benchmark.**

Current state: `backtest/metrics.py` reports only absolute ₹ P&L, win rate,
drawdown, profit factor. There is no way to tell whether the strategy beats
buy-and-hold Nifty, and no Sharpe ratio or annualized return.

**Changes required** (`backtest/metrics.py`, `backtest/engine.py`):

1. Fetch `NSE:NIFTY50-INDEX` (or `NSE:NIFTYBEES-EQ` as a proxy) for the
   backtest date range. Compute buy-and-hold return over the same period.

2. Add to `summarise()` output:
   - `total_return_pct` = `total_pnl_inr / BACKTEST_INITIAL_CAPITAL * 100`
   - `annualized_return_pct` — scale by `252 / trading_days`
   - `benchmark_return_pct` — Nifty buy-and-hold over same period
   - `alpha_pct` — strategy return minus benchmark
   - `sharpe_ratio` — requires per-bar equity curve (see note below)
   - `max_drawdown_pct` — currently in ₹; also express as % of peak equity

3. For Sharpe, the positions report doesn't give a daily equity series. Options:
   - Hook `on_account_state` in the strategy to record equity snapshots.
   - Or post-process: reconstruct an equity curve from cumulative realized P&L
     (sorted by close time — fix T-08 first).

**Files:** `backtest/metrics.py`, `backtest/engine.py`, `backtest/strategy.py`

---

## Priority 3 — Data integrity and fairness

### T-08 · Fix metrics drawdown: sort by close time before cumsum
**Severity: Medium — max drawdown is wrong if the positions report is unordered.**

Current state: `metrics.py:133-142` computes cumulative P&L as
`pnls.cumsum()` without sorting by position close time. If the positions
report returns rows in instrument or internal-id order rather than
chronological order, the equity curve and drawdown are meaningless.

**Fix (`backtest/metrics.py`, `_from_positions`):**
```python
# After parsing pnls, sort by close time if available
if "ts_closed" in df.columns:
    df = df.sort_values("ts_closed")
# Or if using realized_return and NT includes a close timestamp column:
pnls = df.sort_values("ts_closed")["realized_pnl"].apply(_parse_pnl).dropna()
```

Check the actual columns in `generate_positions_report()` output and sort
on whatever close-time column NT provides (likely `ts_closed` or `duration_ns`).

---

### T-09 · Replace survivor universe; reconcile live vs. backtest symbols
**Severity: Medium — you rank one universe and backtest a disjoint one.**

Two separate problems:

**A. Backtest `ALL_SYMBOLS` is survivorship-biased.**
`config.py:28-59` hard-codes 30 names that are today's mega-caps. They were
also mega-caps a year ago, so the bias is mild but real. More critically,
`--all-symbols` is marketed as "fair historical comparison" but uses
today's survivors. For honest backtesting, use a point-in-time index
constituent list (Nifty 50 or 100 membership as of the backtest start date).

**B. Live ranker screens `UNIVERSE_MAX_PRICE ≤ ₹500` (`config.py:124`).**
This excludes most quality large-caps (RELIANCE ≈ ₹1300, TCS ≈ ₹3800, etc.)
and leaves smaller, less liquid names. But `ALL_SYMBOLS` is all expensive
large-caps. **The thing you rank live and the thing you backtest are disjoint.**

**Short-term fix:** Remove or raise `UNIVERSE_MAX_PRICE` so the live universe
overlaps with `ALL_SYMBOLS`. Document why the filter existed.

**Long-term fix:** Source a point-in-time Nifty 50/100 constituent list
(NSE publishes historical index composition) and store it as a CSV. Use that
as the backtest universe instead of the hand-picked `ALL_SYMBOLS`.

**Files:** `config.py`, `universe.py`, optionally a new `data/nifty_constituents.csv`

---

### T-10 · Validate the ranker walk-forward (rank-IC experiment)
**Severity: Medium — the ranker has never been validated.**

Current state: `ranker.py` ranks stocks using today's snapshot. It has never
been tested against forward returns. Weights (40/30/20/10) are unjustified.

**Experiment:**
```python
# scripts/ranker_ic.py — new file
# For each trading day D in a historical window (e.g. last 180 days):
# 1. Rank all symbols using only data up to D (point-in-time).
# 2. Record composite_score for each symbol.
# 3. Record next-day and next-5-day forward return for each symbol.
# 4. Compute Spearman rank-IC = corr(rank, forward_return).
# 5. Plot IC over time; compute mean IC and t-stat.
# → If mean IC ≈ 0, the ranker has no predictive value as-is.
# → If IC > 0.05 consistently, it's worth optimizing the weights.
```

This requires modifying `StockRanker` to accept an `as_of_date` parameter
and fetch data strictly before that date. That's also the prerequisite for
any honest walk-forward combined backtest.

**Files:** `ranker.py`, new `scripts/ranker_ic.py`

---

## Priority 4 — Code quality and operational reliability

### T-11 · Add a test suite
**Severity: Medium — zero tests, core logic untested.**

No tests exist anywhere in the project. The most critical things to test:

```
tests/
├── test_data_loader.py    # IST→UTC conversion round-trips; OHLC consistency
├── test_hmm_model.py      # regime label is one of {Bullish,Sideways,Bearish}
├── test_confluence.py     # all 9 cells return a known signal string
├── test_metrics.py        # "2910.00 INR" parsing; drawdown with known series
├── test_instruments.py    # commission fee is non-zero; lot_size=1
└── test_strategy_sizing.py # max(shares,1) never exceeds notional cap
```

Start with `test_metrics.py` and `test_data_loader.py` — those are pure
functions with no external dependencies and cover the two most error-prone
transformations.

**Files:** new `tests/` directory

---

### T-12 · Add walk-forward / out-of-sample validation
**Severity: Medium — single 90-day in-sample window is meaningless as validation.**

Current state: `engine.py:99-100` defaults to 90 days. A strategy optimized
(even informally, by choosing config params) on 90 days and tested on the same
90 days has zero out-of-sample evidence.

**Minimum viable walk-forward:**
```
Train window: bars[0 : T]           → fit config params / observe behavior
Test window:  bars[T : T+90days]    → report results WITHOUT touching params
Repeat: slide both windows forward by 90 days
```

In practice for this strategy, "fitting" is informal (hand-chosen params),
so the walk-forward is just: run on 4 non-overlapping 90-day periods and
check whether results are consistent. Large variance across periods = overfit.

Add a `--walk-forward` flag to `backtest/__main__.py` that auto-partitions
the date range into N equal windows and runs + reports each separately.

**Files:** `backtest/__main__.py`, `backtest/engine.py`

---

### T-13 · Model Indian-market-specific constraints
**Severity: Low-Medium — `--allow-shorts` maps to no real Indian product.**

Current state: `--allow-shorts` uses `AccountType.MARGIN` with no borrow cost,
no hard square-off at 15:15 enforcement beyond the strategy's own EOD exit,
and no lot-size constraint. Real Indian intraday short strategies require:
- BTST or MIS order type (brokerage-specific, not modeled)
- True hard cut-off enforced by the broker at ~15:10 IST
- For anything beyond one day: F&O (lot sizes, different STT, much higher
  notional per contract)

**Short-term fix:** Add a disclaimer in `__main__.py` and `config.py` that
`--allow-shorts` results are illustrative only and do not map to any real
Indian brokerage product. Disable shorts in the default config
(`BACKTEST_ALLOW_SHORTS = False` is already correct).

**Long-term fix:** Model F&O-equivalent constraints (lot size of 25–75 shares,
margin requirement, futures basis, rollover cost) if short-side research is
genuinely desired.

**Files:** `config.py`, `backtest/__main__.py`

---

### T-14 · Add total cost report and parameter sensitivity output
**Severity: Low — currently no visibility into how much cost drag exists.**

Add to `backtest/metrics.py` `print_summary()`:
- `total_commissions_inr` — how much total cost was paid
- `cost_pct_of_pnl` — cost as fraction of gross P&L (if > 50%, edge is thin)
- `avg_holding_bars` — average bars held per trade (shorter = more sensitive to costs)
- `turnover_pct` — total traded notional / starting capital

Also add a `--sensitivity` flag to `backtest/__main__.py` that runs the
backtest at 0.5×, 1×, 1.5×, and 2× the configured commission rate and
prints a table. Any strategy whose profitability changes sign within 2×
cost uncertainty has no margin of safety.

**Files:** `backtest/metrics.py`, `backtest/__main__.py`

---

## Task summary table

| ID | Task | Priority | Effort | Blocks |
|----|------|----------|--------|--------|
| T-01 | Realistic costs + STT asymmetry | **Critical** | Small | — |
| T-02 | Position size cap + portfolio heat | **Critical** | Medium | — |
| T-03 | Execution timing + intrabar stops | **High** | Medium | — |
| T-04 | HMM label stability check | **High** | Medium | T-05 |
| T-05 | Validate confluence matrix | Medium | Medium | T-04 |
| T-06 | Fix ranker factor scaling + direction | Medium | Small | T-10 |
| T-07 | Nifty benchmark + Sharpe + annualized | Medium | Medium | T-08 |
| T-08 | Fix metrics drawdown sort order | Medium | Small | T-07 |
| T-09 | Fix survivor universe + reconcile live vs. backtest | Medium | Medium | T-10 |
| T-10 | Ranker walk-forward (rank-IC) | Medium | Large | T-06, T-09 |
| T-11 | Test suite | Medium | Medium | — |
| T-12 | Walk-forward / OOS validation | Medium | Medium | T-01, T-02 |
| T-13 | Indian-market short constraints | Low | Small | — |
| T-14 | Cost report + sensitivity output | Low | Small | T-01 |

**Start here:** T-01 → T-02 → T-03. If the strategy survives those three
(positive P&L at realistic costs with capped sizing), everything else is worth
doing. If it doesn't, re-examine the core thesis before proceeding.
