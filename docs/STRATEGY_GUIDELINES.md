# Strategy Development Guidelines

A checklist of hard-won lessons for building quantitative trading strategies
on Indian equity markets. Written for this codebase, but the principles apply
to any systematic strategy.

Use this document at two moments:
1. **Before building** — as a design checklist.
2. **Before trusting a backtest** — as a result-validity checklist.

If a section cannot be answered with evidence (not assumption), the strategy
is not ready to trade real capital.

---

## 1. Define the edge before writing code

A strategy without a stated edge hypothesis is just pattern-matching on noise.

**Write down, in one sentence, why this strategy should make money.**

Bad example: *"The HMM identifies regime, and confluence signals confirm entry."*
That is a mechanism description, not an edge. Indicators do not create edge by
themselves.

Good examples:
- *"Intraday momentum persists for 1–3 bars after a volume surge in large-caps,
  giving us 20–30 bps of directional drift before mean-reversion sets in."*
- *"At structural support in a Bullish regime, institutional buyers absorb supply.
  The imbalance resolves upward with higher probability within 4 bars."*

Then ask: **what evidence would falsify this hypothesis?** If you cannot name
a falsifiable test, the hypothesis is not scientific.

**Questions to answer before starting:**

- What is the expected holding period?
- What is the expected per-trade edge in basis points?
- What is the cost budget (round-trip, realistic)?
- Is edge > cost + 2× standard error?
- Who is on the other side of this trade, and why are they wrong?

---

## 2. Cost realism — NSE intraday

**The most common way quantitative strategies die is unrealistic costs.**

Assume all-in round-trip costs of **25–35 bps** for NSE intraday equity before
you evaluate any backtest result. For mid/small-caps, use 40–60 bps.

### Full NSE cost breakdown

| Component | Direction | Amount |
|-----------|-----------|--------|
| STT | Sell-side only (intraday delivery) | 2.5 bps |
| Exchange transaction charge | Both sides | ~0.30 bps/leg |
| SEBI turnover charge | Both sides | ~0.01 bps/leg |
| Stamp duty | Buy-side only | ~0.30 bps |
| GST 18% on brokerage + exchange | Both sides | ~0.5 bps effective |
| Brokerage | Both sides | ₹20/order flat (discount) or 3–10 bps (full-service) |
| Bid-ask half-spread | Both sides | 2–5 bps (Nifty 50); 5–20 bps (mid/small) |
| Market-order slippage | Both sides | 1–5 bps (scales with order size) |

**Key rules:**
- STT is **sell-side only and asymmetric** — do not model as symmetric maker/taker.
- For delivery (overnight holds), STT is 10 bps on **both sides** — far higher.
- Flat ₹20/order brokerage becomes dominant when trade size < ₹100,000.
- **Always model bid-ask spread explicitly.** Using bar close prices assumes
  you transact at mid, which is impossible on a market order.
- Test profitability at 1×, 1.5×, and 2× your estimated cost. A strategy that
  breaks even within 2× cost uncertainty has no margin of safety.

---

## 3. Backtest validity checklist

Run through every item before reporting a backtest result.

### 3a. Look-ahead bias
- [ ] Signals use only data available up to bar *i* — never bar *i+1* or later.
- [ ] Feature scaling (e.g. StandardScaler) is fit on the in-window data only,
      not on the full dataset.
- [ ] Signal computation timestamp ≠ fill timestamp. The decision at bar *i*'s
      close can only be executed at bar *i+1*'s open (or later).
- [ ] Any "current regime" label is computed before the bar closes, not after.

### 3b. Survivorship bias
- [ ] The backtest universe is a **point-in-time** constituent list —
      symbols that existed and were liquid *at the start of the backtest period*,
      not today's survivors.
- [ ] If using a fixed watchlist, document that it is survivorship-biased and
      that results will be optimistic.
- [ ] The live-trading universe and the backtest universe overlap substantially.
      If they are disjoint (different price ranges, market caps, or screens),
      the backtest result does not apply to live trading.

### 3c. Fill and execution realism
- [ ] Entries and exits use the **next bar's open**, not the decision bar's close.
- [ ] Stops check intrabar (bar low/high), not just the closing price. When a
      stop is triggered intrabar, the fill price is the stop price, not the close.
- [ ] Position size is capped at a realistic fraction of the bar's volume
      (e.g. 5–10% participation). Fills beyond ~10% of bar volume are fantasy.
- [ ] Market orders in an intraday context have a modeled half-spread cost.
- [ ] Commissions are applied asymmetrically where the real fee structure demands it.

### 3d. Data integrity
- [ ] OHLC consistency enforced: `high >= max(open, close)`,
      `low <= min(open, close)`. Violated bars should be dropped, not silently
      coerced, or at minimum flagged.
- [ ] Volume = 0 or missing bars are treated as illiquid, not filled as
      volume-1 placeholders.
- [ ] Timezone conversion is verified: confirm that a known market event
      (e.g. 09:15 IST open) lands at the expected UTC timestamp.
- [ ] Daily and intraday bars are from the same data source and consistent.

### 3e. Position sizing and portfolio constraints
- [ ] A single position cannot exceed N% of portfolio equity (suggested: 10–15%).
- [ ] A single position cannot exceed M% of the bar's volume (suggested: 5–10%).
- [ ] Total gross exposure across all positions is capped (suggested: 80–100%).
- [ ] In a portfolio backtest with correlated instruments, aggregate directional
      exposure is checked — not just per-position risk.
- [ ] When price is near a stop (small stop distance), the position-size formula
      can produce leverage. Add a hard notional cap independent of stop distance.

---

## 4. Signal and model validity

### 4a. Every model assumption is a liability
Before using a statistical model, state its assumptions and check each one:

| Model/method | Key assumptions | How to check |
|-------------|-----------------|--------------|
| Gaussian HMM | Stationary emission distributions; Markov transitions | Ljung-Box on residuals; regime-split feature distributions |
| Gaussian HMM | Fixed number of states | BIC/AIC across K=2,3,4 |
| ATR / Keltner bands | Stationary volatility | Rolling ATR plot |
| Linear momentum | Autocorrelated returns | ACF/PACF of returns |
| Any classifier | IID samples | Check for serial correlation in features |

**Specific HMM cautions:**
- Per-bar refitting on an expanding window produces label-switching. State
  "Bullish" at bar *i* may not mean the same thing as "Bullish" at bar *i+1*
  if EM converges to a different local optimum. Measure this explicitly.
- Re-fitting the feature scaler on expanding data shifts the feature space
  continuously. This is not look-ahead bias, but it makes consecutive model
  fits non-comparable.
- Minimum sample for a 3-state diagonal Gaussian HMM: at least 10× the
  number of free parameters. For 3 states × 2 features: ≥ 240 samples minimum
  (prefer 500+).
- Time-of-day patterns (open auction volatility, lunchtime lull) are not
  stationarity-preserving across the intraday session. Either include
  time-of-day as a feature or segment the session explicitly.

### 4b. Hand-authored signal tables must be validated
A lookup table (like a regime × location → signal matrix) is a hypothesis,
not a fact. Before trading it:

- Compute the mean forward return for each cell over historical data.
- Compute t-statistics. Cells without a statistically significant forward
  return edge should be treated as NEUTRAL.
- Check for internal consistency: if "Bullish + At Resistance → exit,"
  verify that this cell actually has lower forward returns than "Bullish + At
  Support → entry."
- Re-validate after every significant market regime change (post-COVID,
  post-rate-cycle, etc.) — a table calibrated in one market environment
  may be inverted in another.

### 4c. Composite scores need factor validation
When combining multiple signals into a score:

- Measure each factor's **information coefficient (IC)** against forward returns
  independently before combining. Factors with IC ≈ 0 add noise, not signal.
- Factors on different scales should be **explicitly normalized** before
  weighting. A 0–1 factor and a -1 to +1 factor contribute differently to a
  weighted sum even at equal weights.
- Factors that are always positive (never penalize) systematically inflate scores
  and add bias. Volume surge and proximity are examples — they should be signed
  to reflect direction (a selling-climax volume surge is bearish, not neutral).
- Weight optimization requires out-of-sample validation. Weights chosen by
  intuition should be treated as the starting point for a sensitivity analysis,
  not the final answer.

---

## 5. Risk management defaults

Apply these limits by default. Relax only with documented justification.

### Per-trade limits
| Parameter | Default | Rationale |
|-----------|---------|-----------|
| Max risk per trade | 1–2% of equity | Kelly fraction for strategies with win rate < 60% |
| Max position notional | 10% of equity | Concentration limit |
| Max volume participation | 5% of bar volume | Beyond this, you move the market |
| Stop placement | Beyond a structural level, not a round % | Round % stops cluster and get hunted |

### Portfolio limits
| Parameter | Default | Rationale |
|-----------|---------|-----------|
| Max gross exposure | 80% of equity | Reserve for adverse moves |
| Max sector concentration | 30% of equity | NSE large-caps are highly correlated |
| Max correlated exposure | One "bet" per correlation cluster | All Nifty longs in a bull regime = one bet |
| Daily loss limit | 3–5% of equity | Halt trading if breached |
| Max consecutive losses | 5 | Re-evaluate before continuing |

### Stop and exit discipline
- Set stops **before entry**, not after.
- Stop distance drives position size — do not size first and then place a
  convenient stop.
- A stop near current price (< 0.5%) produces outsized position sizes.
  Cap the minimum stop distance regardless of structure.
- EOD flatten for intraday strategies eliminates overnight gap risk.
  If carrying overnight, model gap risk explicitly.

---

## 6. The ranker / candidate selection trap

Daily ranking systems are prone to a specific form of look-ahead bias that is
easy to miss: **using today's rank to select symbols for a historical backtest.**

The rule: **the symbol selected on day D must have been rankable on day D using
only data available on day D.**

This requires:
- Point-in-time constituent lists (which symbols existed and were liquid on day D)
- Point-in-time signal computation (HMM fit using only data up to day D)
- Point-in-time structure levels (ATR/pivots using only data up to day D)

Without this, the ranker is decoration — it selects today's winners and
attributes past performance to a selection that was impossible to make historically.

**Before trusting a ranker:**
- Compute rank-IC (Spearman correlation of rank with forward N-day return)
  over a walk-forward window.
- Mean IC > 0.05 with t-stat > 2 is a minimum bar for the ranker to be
  considered informative.
- IC should be positive and consistent across market regimes (bull/bear/sideways).

---

## 7. Validation hierarchy

A strategy is only as good as the worst validation it has passed. Progress
through these stages in order — do not skip ahead.

```
Stage 1: Logic check
  → Can you explain, in plain English, why each rule should make money?
  → Does the code implement exactly what you described?
  → Are all look-ahead and survivorship guards in place?

Stage 2: Cost survival
  → Is the strategy profitable at 1.5× and 2× estimated costs?
  → If not, stop here.

Stage 3: In-sample statistical validity
  → Are the signal cells significantly different from zero (t-stat > 2)?
  → Are model assumptions met (stationarity, sample size, label stability)?
  → Is position sizing bounded and realistic?

Stage 4: Out-of-sample validation
  → Run on a held-out period (min 6 months) with zero parameter changes.
  → Compare Sharpe, win rate, profit factor to in-sample results.
  → Sharpe degradation > 50% = overfitting.

Stage 5: Walk-forward
  → Run N non-overlapping windows (min 4). Results should be consistent.
  → High variance across windows = parameter sensitivity / overfitting.

Stage 6: Benchmark comparison
  → Does the strategy beat buy-and-hold Nifty 50 on a risk-adjusted basis?
  → If Sharpe(strategy) < Sharpe(Nifty), you are taking more risk for less return.

Stage 7: Paper trading (forward test)
  → Run live signals for 1–3 months without capital at risk.
  → Compare live signal distribution to backtest signal distribution.
  → Unexplained divergence = regime change or data pipeline issue.

Stage 8: Live trading (small size)
  → Start at 10–20% of intended size.
  → Verify fills match assumptions.
  → Scale up only after 3+ months of consistent live performance.
```

---

## 8. Indian market specifics

These are non-negotiable constraints for NSE equity strategies.

### Short selling
- **Cash segment intraday (MIS)**: allowed, but must be squared off same day.
  Brokers enforce hard cut-off at ~15:10 IST. No carry-forward.
- **Delivery short**: not possible in Indian cash equity — you must own shares
  to sell.
- **F&O (futures/options)**: the only product for multi-day short exposure.
  Lot sizes (25–75 shares typically), margin requirements, daily MTM settlement,
  and rollover costs all apply. A cash-equity backtest does not model F&O.
- **Default**: `allow_shorts = False` for cash-segment strategies. Any short-side
  result should be labeled "illustrative only" unless F&O constraints are modeled.

### Liquidity constraints
- **Circuit limits / price bands**: NSE imposes 5%/10%/20% daily price bands.
  A position hitting a lower circuit cannot be exited until the band opens.
  Model this by rejecting fills when the bar's return exceeds the circuit limit.
- **Lot size**: NSE minimum lot is 1 share for most equities. F&O has fixed lot
  sizes — use the correct lot size for the product being modeled.
- **Market depth**: for names outside Nifty 100, intraday volume can be thin.
  Participation cap of 5% of bar volume is more important in mid/small-caps.
- **NSE trading hours**: 09:15–15:30 IST, Monday–Friday. Pre-open session
  09:00–09:15 IST uses a call auction — do not model pre-open fills as
  continuous-market fills.

### Timezone and settlement
- All IST timestamps are UTC+5:30. Subtract 5h 30m to convert to UTC.
- NSE uses T+1 settlement (as of January 2023). Overnight positions require
  actual capital, not just margin.
- Public holidays vary by year — use the NSE holiday calendar, not a generic
  5-day trading week.

---

## 9. What good documentation looks like

Every strategy file should answer these questions in its docstring or README:

1. **Edge hypothesis**: why should this make money?
2. **Entry rules**: exact conditions, in plain English and code.
3. **Exit rules**: all exit paths (signal, regime, stop, EOD, time).
4. **Position sizing formula**: what drives size, what caps it.
5. **Cost assumption**: what commission rate was used, and is it realistic?
6. **Universe**: what symbols, what period, is it survivorship-biased?
7. **Validation status**: which stages in Section 7 have been passed?
8. **Known limitations**: what does this NOT model that matters?
9. **Parameters**: which are stable vs. sensitive? Has sensitivity been checked?

If any of these cannot be answered, the strategy is not production-ready.

---

## Quick reference — red flags in any backtest result

If you see any of these, investigate before trusting the result.

| Red flag | Likely cause |
|----------|-------------|
| Win rate > 70% on an intraday strategy | Look-ahead bias or stop on close |
| Profit factor > 3 | Look-ahead bias, low trade count, or survivorship |
| Max drawdown < 5% over 90 days | Too few trades or look-ahead |
| Results dramatically better in bull markets | Beta, not alpha |
| Strategy works on large-caps but not mid-caps | Liquidity artifact |
| Adding more symbols always improves results | Diversification != edge |
| Performance stable across all parameter values | Overfitted to a robust-looking region |
| Performance collapses outside the backtest window | Overfitting / regime-specific |
| Cost sensitivity: 2× cost → unprofitable | No margin of safety |
| Position sizing produces > 20% notional in one name | Uncapped sizing bug |
| Strong daily-bar IC for an *intraday* strategy | Return may accrue at the open-auction print or a minute you can't trade — validate entry/exit timing on intraday bars before trusting it (see GAP_FADE_THESIS §8) |

---

## 10. Case study — HMM-confluence strategy postmortem (2026-06)

A worked example of the principles above, from a real backtest of
`HMMConfluenceStrategy`. Recorded so future strategies don't repeat the same
failures. **None of the symbols tested were profitable** — but the value is in
*why*, and which failures were bugs vs. which were absence-of-edge.

### Setup
- 15-min entries gated by 60-min HMM regime; ranker's top-5 picks, then all 30
  `ALL_SYMBOLS`; 90-day window (2026-03 → 2026-05); shorts enabled.

### Headline result
| Metric | Value |
|--------|-------|
| Symbols profitable | 0 / 29 (full run), 0 / 5 (top-5 run) |
| Mean return (90d) | −5.8% (all) / −9.3% (top-5) |
| Win rate | ~5–11% |
| Profit factor | ~0.07 |
| Trades to land one win | **~19:1** |
| Avg win : avg loss | **~0.6 : 1** (winners *smaller* than losers) |
| Cost as % of gross P&L | **~48%** |

### Failure modes observed (each maps to a section above)

1. **Regime label churn → noise signal** (§4a). The HMM was refit cold on an
   *expanding* window every bar; EM landed on a different local optimum each
   time, so "Bullish" at bar *i* ≠ "Bullish" at bar *i+1*. Measured **50–64%
   label-flip rate** (the code flags >20% as instability). Entries fired on
   random flickers.
   **Fix that worked:** warm-start each refit from the previous bar's params
   (`HMMModel(warm_start=True)`) + cap the window (`HMM_MAX_WINDOW=500`).
   60-min flip rate dropped **55% → 13%**. *Necessary but not sufficient* — the
   strategy still lost. Stabilizing a signal does not give it edge.

2. **No re-entry cooldown → overtrading** (§5 stop discipline, §3c). The worst
   blow-up (WIPRO: **398 trades**, −31%) had the *lowest* regime churn of the
   group. Cause: when the regime sits Bullish and the 15m signal stays STRONG
   BUY, the strategy re-enters the bar after every stop-out, looping until EOD.
   **Lesson:** a persistent signal + tight stop + no cooldown = death by a
   thousand cuts. Always gate re-entry on a cooldown or a *signal change*, not
   signal *presence*.

3. **Costs ~48% of gross** (§2). Direct consequence of #2. At ~25–37 bps/leg,
   overtrading made costs structurally fatal regardless of signal. A strategy
   trading 75–400×/90d per name cannot survive NSE costs.

4. **Inverted payoff** (§5). Avg win < avg loss (~0.6:1) *and* a 5% hit rate —
   negative on both axes. Cause: `TAKE PROFIT`/regime-flip exits cut winners
   early while stops + EOD-flatten realized full losses. **Lesson:** asymmetric
   exits must favor the winner (let it run via trailing/ATR target), not the
   loser. To break even at a 5% hit rate you'd need ~17:1 payoff; we had 0.6:1.

5. **Caught between intraday and swing** (§5). Support-based (positional-scale)
   stops combined with a 15:15 EOD flatten — neither a clean scalper nor a swing
   system. Pick one horizon and make stops/targets/exits consistent with it.

6. **Entry filter too loose** (§4b). `signal_15m` was STRONG BUY ~69% of bars.
   A condition that's true two-thirds of the time selects almost nothing.

### Infrastructure bugs found (separate from strategy edge)
- **Commission silently reported as ₹0.** The NT positions report returns
  `commissions` as a *list* (`['740.42 INR']`); the parser did
  `str(val).strip("[]").split()[0]` → `"'740.42"` → `float()` failed → NaN → 0.
  Costs *were* charged (realized_pnl is net) but invisible in the report. **A
  cost column reading exactly 0.0 is a red flag — verify the parser, not the
  fees.** (§2)
- **Ranker crashes on an empty universe.** On non-trading days the Nifty-500
  filter returns 0 symbols → empty `scores_df` → `KeyError: 'direction'`. Guard
  selection code against empty inputs.
- **Log spam dominated output.** hmmlearn emitted 60–80% of all log lines as
  benign "not converging" messages (through its *logger*, not the warnings
  module). Silenced via `logging.getLogger("hmmlearn").setLevel(logging.ERROR)`.

### The meta-lesson
The strategy had **two independent problems**: mechanical bugs that bleed money
(overtrading, inverted payoff, costs) and an **unverified entry edge**. Fixing
the bugs can move the result from −9% toward break-even, but cannot make it
*positive* — that requires the signal to actually predict forward returns.
**Before polishing execution, run the edge test** (`scripts/ranker_ic.py`,
rank-IC vs forward return — §4c, §6). If mean IC ≤ 0, the features (here: only
log-return + range-ratio) are the problem, and no amount of stop/cost tuning
will save it. Order of operations: **prove edge first, then fix execution.**

### Edge verification — what the tests actually showed
We then ran the edge tests. They are the most important part of this case study.

1. **Ranker-IC = no edge.** `scripts/ranker_ic.py` (point-in-time score vs
   next-day return, Spearman): **mean IC −0.008, t −0.06**, IC>0 on 45% of days.
   The composite score is statistically indistinguishable from random. This,
   not the backtest P&L, is the root finding: the signal carries no information.

2. **The mechanical fixes behaved exactly as theory predicts.** Re-running the
   fixed strategy: mean return −9.3% → −5.0%, WIPRO's runaway 398→177 trades.
   But **profit factor (0.07) and cost ratio (49%) were unchanged.** Execution
   fixes cut the *loss rate*; they cannot create edge. Proof, in one experiment,
   that you cannot tune your way out of a zero-IC signal.

3. **Feature screen (`scripts/feature_ic.py`).** Tested 9 candidate daily
   features individually. The HMM's own inputs were confirmed dead
   (`range_ratio` IC≈0, `ret_1d/5d` slightly negative). One lead appeared —
   volume z-score, IC +0.056 on 8 symbols — then **flipped to −0.019 when
   widened to 28 symbols.** A small-sample mirage.

4. **Reversal lead, killed out-of-sample (`scripts/reversal_test.py`).** A
   1-day reversal long/short (long losers, short winners) looked great over a
   5-month window: gross +36% ann, Sharpe 1.3. Two problems killed it:
   (a) break-even cost was only ~12 bps at the 1-day turnover it needed vs
   ~25–50 bps real cost; (b) extended to a **full year it vanished entirely**
   (gross −0.3%, t −0.02; sign even flipped at 5-day hold). The 5-month result
   was a regime artifact.

### The lesson that generalizes beyond this strategy
**Promising signals on small samples evaporate when you add data — we saw it
twice (volume z-score, then reversal).** This is the single most important
research habit: *test cheap and small to generate candidates, but never trust a
lead until it survives a wider universe AND an out-of-sample window.* The cost
of catching both mirages was a few daily-data fetches; the cost of not catching
them would have been a deployed losing strategy.

**Final verdict for this approach:** no robust tradable edge exists on NSE
large-caps using daily price/volume features, in either direction (momentum
loses, reversal is period-specific and cost-killed). A future attempt needs a
genuinely different ingredient — higher-dispersion universe (mid/small-caps),
different data (intraday microstructure, events, fundamentals), or a
low-turnover horizon where costs stop dominating — **not** a different model on
the same inputs.
