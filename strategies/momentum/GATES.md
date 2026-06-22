# Momentum Strategy — Gate-by-Gate Specifications

Following the framework: hypothesis → triage → vectorized → backtest → sandbox → live

---

## GATE 0: Hypothesis (CURRENT — locked)

**Edge statement:**
> Nifty 500 constituents exhibit 12-1 month cross-sectional momentum: stocks ranked by 12-month total returns, excluding the past month, deliver predictable outweekly continuation. Factor exposure (quality, low vol, size) drives the outperformance. Turnover filter (rebalance only if drift > 1.5%) throttles costs to below the edge.

**Other side:** Retail investors underweight quality stocks; factor mean-reversion is slower than monthly rebalance cadence.

**Falsifiers (kill the entire hypothesis):**
- Gross Sharpe < 0.8 in-sample on 2005–2020 data
- IC (Spearman) of 12-1 rank vs future returns < 0.02 (statistically insignificant)
- Edge disappears after realistic costs (40–65 bps round-trip)
- Parameter sensitivity sharp peak (only 12-1 works, 11-1 and 13-1 fail drastically)

**Evidence to collect (Hypothesis stage):**
- IC of 12-1 rank vs one-month-forward returns across Nifty 500
- Historical Sharpe of naive equal-weight quintile strategy
- Survivorship bias check (include delisted names)
- Parameter stability (try 11-1, 12-0, 12-2, 13-1)

**Next gate:** IC ≥ 0.03 (5+ t-stat) → advance to TRIAGE

---

## GATE 1: Triage (Raw IC, no-fills edge check)

**Objective:** Quick IC test to confirm the signal exists before building the backtest engine.

**Tests to run:**

### 1a. Rolling IC (12-1 rank vs 1-month return)
- Weekly rebalance: for each Friday EOD, rank Nifty 500 by 12-1 return
- Wait for next 1 month of returns, compute Spearman IC
- Rolling window: 2005–present, non-overlapping weeks
- **Gate:** IC mean ≥ 0.03, IC t-stat ≥ 2.0 (p < 0.05)

### 1b. IC stability across regimes
- Compute IC separately for:
  - Bull market (Nifty 500 ≥ 200-MA)
  - Bear market (Nifty 500 < 200-MA)
  - High-vol regime (VIX-analog ≥ median)
  - Low-vol regime (VIX-analog < median)
- **Gate:** IC ≥ 0.02 in ≥ 3 of 4 regimes

### 1c. Decay test (does rank age matter?)
- Compute IC at 1-week, 2-week, 4-week forward return horizons
- **Gate:** IC doesn't collapse at 4 weeks (IC >= 0.60 × 1-week IC)

### 1d. Quintile spread
- Split Nifty 500 into 5 quintiles by 12-1 rank
- Compute mean 1-month return for each quintile
- Plot: Q1 (worst) → Q5 (best)
- **Gate:** Q5 > Q1 by ≥ 2% annualized (≥ 0.17% monthly) after bid-ask

### 1e. Survivorship bias check
- Backtest universe: Nifty 500 constituents at each date (point-in-time)
- Historical universe: same, including delisted names
- Compare IC (should be similar; if IC jumps after adding delisted, survivorship bias exists)
- **Gate:** IC difference < 10% (robust to delisting)

**Output:** IC report, regime breakdown, quintile spread plot

**Pass/fail criteria:**
- ✅ **PASS** → Advance to VECTORIZED
  - IC ≥ 0.03, t-stat ≥ 2.0
  - Stable across ≥ 3 regimes
  - Doesn't decay significantly by week 4
  - Q5-Q1 spread ≥ 2% annualized post-costs
  - Robust to survivorship

- ❌ **FAIL** → Kill hypothesis
  - IC < 0.02 (no statistical signal)
  - Highly regime-dependent (e.g., only works in bull market)
  - Edge is a lead (future data pollution)
  - Large survivorship bias

---

## GATE 2: Vectorized (Full-data signal, expanding window, no look-ahead)

**Objective:** Build the full 12-1 signal compute pipeline with strict no-look-ahead enforcement.

**Implementation checklist:**

### 2a. Universe registry
- NSE point-in-time Nifty 500 constituent history (ISIN keying)
- Delisted names with exit dates
- Store in SQLite
- Query: `universe_at_date(d)` → list of ISINs + weights

### 2b. Total return series
- OHLCV from Bhavcopy (Fyers API or archive)
- Corporate actions (splits, bonuses) from NSE master
- Restatement: historical prices adjusted for corporate actions
- Daily total returns: `(close_t - close_{t-1}) / close_{t-1}`
- **Check:** First split/bonus date should show as price discontinuity before adjustment, no discontinuity after

### 2c. 12-1 momentum compute (expanding window, no look-ahead)
```python
def compute_signal(isin, dates):
    """For each date d in dates:
       - Lookback: date d minus 12 months
       - Ranking window: d-12m to d-1m (exclude past month)
       - Return: 12m return, then rank percentile vs universe at d
    """
    for d in dates:
        lookback_start = d - 12*30 days (approx)
        lookback_end = d - 1*30 days
        price_start = get_price(isin, lookback_start)
        price_end = get_price(isin, lookback_end)
        ret_12_1 = (price_end - price_start) / price_start
        # Rank vs universe_at_date(d)
        percentile = rank(ret_12_1, all_returns_at_d)
        return percentile
```

**Validation:** For each week:
- Check that signal uses only data up to Friday EOD
- Check that signal does NOT use data from the next Friday onwards
- Compare to triage IC (should match; if not, look-ahead bug exists)

### 2d. Signal stability
- Check that week-to-week signal rank correlation ≥ 0.60 (not random)
- Check that top 20% stocks in week N overlap ≥ 40% with week N+1 (continuity)
- **Gate:** Correlation ≥ 0.60

### 2e. Cache & performance
- Cache signal outputs (12-1 rank, percentiles) to disk, keyed by date
- Compute time per week should be < 10s (or precompute all weeks)
- **Gate:** Compute time < 1 min for full 2005–present

**Output:** Signal database (SQLite or Parquet), cache structure

**Pass/fail criteria:**
- ✅ **PASS** → Advance to BACKTEST
  - Signal computes with no look-ahead (validated)
  - IC matches triage result (same underlying computation)
  - Signal is stable week-to-week (corr ≥ 0.60)
  - Cache is fast and reliable

- ❌ **FAIL** → Debug and loop
  - IC diverges from triage (look-ahead bug or data mismatch)
  - Signal is too noisy (corr < 0.40)
  - Corporate actions not handled correctly (price jumps visible)

---

## GATE 3: Backtest (NautilusTrader, VWAP fills, portfolio-level)

**Objective:** Realistic EOD portfolio backtest with cost model, position sizing, turnover gate.

**Implementation:**

### 3a. Backtest harness
- Use `core.backtest.engine` (NautilusTrader BacktestEngine)
- Portfolio-level: shared capital, vol-weighted position sizing
- Daily EOD bars (IST 3:30 PM → UTC 10 AM previous session)
- Rebalance: every Friday EOD

### 3b. Turnover gate
- Current portfolio: 100 stocks @ equal weight (or vol-weighted)
- Target portfolio: top 100 stocks by 12-1 rank
- Trades to execute: new positions (buy) + deltas (sell overweight)
- Filter: drop all trades if total notional traded < 1.5% of portfolio
- **Rationale:** Below 1.5%, costs eat more than the edge

### 3c. Cost model
```python
cost_per_leg_bps = 35  # STT 5 + exchange 10 + half-spread 15 + slippage 5
round_trip_bps = 70

entry_cost = buy_qty * buy_price * cost_per_leg_bps / 1e4
exit_cost = sell_qty * sell_price * cost_per_leg_bps / 1e4
net_return = (exit_price - entry_price) / entry_price - round_trip_bps / 1e4
```

### 3d. Fills
- Entry: next-day open @ 09:15 IST
- Exit: 1 week later, open @ 09:15 IST
- VWAP model: use intraday volume, fill at day's VWAP (conservative)
- **Check:** Realized slippage < 10 bps (reasonable for NSE mid-caps)

### 3e. Position sizing
- Equal-weight: 1/100 of portfolio per stock
- OR vol-weighted: size inversely to trailing 20-day volatility
- Max single position: 5% of portfolio
- Portfolio-level turnover cap: don't trade if drift < 1.5%

### 3f. Backtests to run
1. **Walk-forward 2005–2015 (in-sample):** train on this, report Sharpe, maxDD
2. **Validate 2015–2020 (out-of-sample):** should be OOS Sharpe ≥ 0.60×IS
3. **Test 2020–present (recent OOS):** should maintain edge
4. **Parameter sweep:** 11-1, 12-0, 12-1, 12-2, 13-1 windows → should show plateau, not sharp peak
5. **Detrending:** remove trend from Nifty 500 returns, backtest signal on detrended; should survive

**Output:** Backtest report (Sharpe, maxDD, win%, monthly/annual returns)

**Pass/fail criteria:**
- ✅ **PASS** → Advance to SANDBOX
  - In-sample Sharpe ≥ 0.6
  - OOS Sharpe ≥ 0.3 (1 SE haircut from IS)
  - Max drawdown ≤ 15%
  - Win rate ≥ 52%
  - No parameter cliff (12-1 is better, but 11-1 & 13-1 are within 20% Sharpe)
  - Signal survives detrending
  - Realized costs match model ±10%

- ❌ **FAIL** → Kill strategy
  - IS Sharpe < 0.5 (weak signal)
  - OOS Sharpe < 0.1 (overfit)
  - Parameter cliff (12-1 works, everything else fails) → overfit
  - Doesn't survive detrending (signal is just trend-following)
  - Costs exceed model by 2× (execution issues)

---

## GATE 4: Sandbox (Paper trade 2–3 months, ≥ 10 rebalances)

**Objective:** Forward-looking validation with live Fyers data, before real capital.

**Setup:**
- Live EOD data via Fyers API
- Weekly 12-1 compute on live data
- Generate target portfolio (top 100)
- Simulate fills at next-day open (VWAP forecast)
- Track P&L, costs, slippage

**Metrics to monitor:**
- Realized weekly P&L vs backtest expectation
- Realized costs vs model (should match)
- Position-level fill quality (slippage < 10 bps)
- Win rate (% of weeks with positive P&L)

**Pass/fail criteria:**
- ✅ **PASS** → Advance to SHADOW
  - Realized Sharpe matches backtest ±1 SE
  - Realized costs match model ±15%
  - No systematic slippage exceeding model
  - Win rate ≥ 50% (consistent with backtest)
  - No kill-criteria fire (drawdown, win-rate collapse)

- ❌ **FAIL** → Loop or kill
  - Costs exceed model by 2× (market conditions different, illiquidity)
  - Realized Sharpe 50%+ below backtest (overfit)
  - Consistent negative P&L despite positive backtest (data mismatch)

---

## GATE 5: Shadow Live (1–3 months, ≥ 8 rebalances @ 10% sizing)

**Objective:** Real market fills, 10% portfolio sizing, before scaling.

**Setup:**
- Same weekly rebalance, 10% position sizing
- Real Fyers fills (no simulation)
- Track TCA (transaction cost analysis) vs model
- Kill-switch armed

**Metrics:**
- Realized fill prices vs VWAP model
- Slippage breakdown (partial fills, market impact)
- Drawdown (should be ≤ backtest maxDD at 10% scale)
- Win rate

**Pass/fail criteria:**
- ✅ **PASS** → Advance to LIVE (scale to 100%)
  - Realized fills within 2× model std dev
  - Drawdown ≤ 12% (less than hard 15% stop)
  - Win rate ≥ 48% (allows small margin below backtest)
  - No kill-criteria fire

- ❌ **FAIL** → Pull plug or loop to paper
  - Fills consistently worse than model (illiquidity)
  - Drawdown approaching 15% (kill-switch zone)
  - Win rate < 45% (edge worse than expected)

---

## GATE 6: Live (100% sizing, full capital)

**Objective:** Full deployment with mechanical kill-switch.

**Setup:**
- 100% position sizing
- Weekly Friday 3:30 PM IST rebalance
- Kill-switch: drawdown > 15%, win rate < 45% trailing 20, slippage 2×, rolling IC < 0 (3-month)
- Monthly IC recompute (catch regime breaks)

**Monitoring:**
- Daily P&L, positions, universe changes
- Weekly rebalance log, fills
- Monthly IC check (quintile spread degradation signal)
- Kill-switch status

**Exit criteria (kill-switch):**
- Equity drawdown > −15% → halt
- Trailing-20 win rate < 45% → halt
- Realized costs 2× model → halt
- Rolling 3-month IC < 0 → halt

---

## Specifics: Parameters (Locked)

```python
# Core strategy
lookback_months = 12
ranking_months = 1
quintile = 1  # top 20%
target_hold_count = round(500 / 5) = 100
rebalance_freq = "weekly"  # Friday EOD

# Position sizing
equal_weight_per_stock = 1 / 100 = 1%
max_single_position = 5%

# Turnover gate
turnover_threshold_pct = 1.5

# Cost model (bps per leg)
stt_bps = 5
exchange_bps = 10
half_spread_bps = 15
slippage_bps = 5
round_trip_bps = 70

# Kill-switch (manifest.py)
drawdown_limit = 0.15
trailing_winrate_window = 20
trailing_winrate_floor = 0.45
rolling_ic_window = 13*4 = 52  # 3 months

# Fill model
fill_model = "vwap"  # next-day open assumed at VWAP
look_back_after_entry = "never"  # exit only at scheduled rebalance
```

---

## Current Status

**Stage:** hypothesis (locked, ready to move to GATE 1: TRIAGE)

**Next step:** Collect IC evidence (GATE 1) to confirm edge before building the backtest engine.

**Timeline estimate:**
- Triage: 1 week (IC compute, regime tests)
- Vectorized: 1 week (signal pipeline, validation)
- Backtest: 1–2 weeks (harness setup, walk-forward)
- Sandbox: 2–3 months (paper trade)
- Shadow: 1–3 months (10% real)
- Live: ongoing (daily monitoring, monthly IC recheck)
