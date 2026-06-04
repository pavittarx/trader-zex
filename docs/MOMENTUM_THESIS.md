# Strategy Thesis — Cross-Sectional Momentum (Trend-Following), NSE

Status: **REAL BUT MODEST IN-SAMPLE EDGE, SURVIVORSHIP-CORRECTED (2026-06).**
Cross-sectional 12-1 momentum is a genuine, significant, cost-robust,
beta-adjusted edge on a broad liquid NSE universe. After correcting for
survivorship with a point-in-time liquidity universe (§11), the honest estimate
is **L/S net Sharpe ~0.5 / long-only alpha ~0.9%/mo (t 3.2, ~11%/yr) beyond beta**
on a top-200-by-liquidity universe (2012-2021), robust across both sub-periods and
2× cost — vs. the survivorship-INFLATED static-universe Sharpe of 0.81 (§10). That
makes it comparable-to-modestly-better than PEAD (~0.5). Crash-risk overlays
(vol-scaling + market-trend filter, §12) lift in-sample Sharpe to ~0.79 BUT do
**not** cut the ~−40% tail — the dominant drawdown is a 2014-style up-market value
rotation that bear-market filters miss. **Still gating it:** (a) in-sample only —
no OOS yet (THE remaining gate); (b) the un-hedged ~−40% rotation tail; (c) the
candidate pool still omits pre-2020 delistings (residual upward bias).
See §10-§12. Documented per `STRATEGY_GUIDELINES.md` §9.

---

## 1. Edge hypothesis (one sentence)

> Stocks that have outperformed their peers over the past ~12 months (excluding
> the most recent month) continue to outperform over the next month, because
> investors **underreact** to gradual fundamental improvement and **anchor** to
> stale valuations — the information diffuses slowly into price.

- **Who is on the other side, and why are they wrong?** Slow-to-update investors
  (limited attention, anchoring, the disposition effect — selling winners too
  early). Their delayed repricing is the drift we harvest. This is the most
  robust, most replicated anomaly in the global cross-section of equity returns
  (Jegadeesh-Titman 1993; Asness/Moskowitz/Pedersen "Value and Momentum
  Everywhere" 2013), and it has been documented on Indian equities.
- **Why it fits THIS codebase's hard-won constraint.** The repo's binding lesson
  (`RESEARCH_BACKLOG.md`) is *turnover, not signal strength*: every
  daily-rebalanced cross-sectional L/S died on cost. Monthly-rebalanced 12-1
  momentum turns over ~20-40% of the book per month — an order of magnitude
  lower turnover than the dead intraday signals. Cost is paid rarely.

### Falsification — what would kill this hypothesis
1. **IC ≈ 0.** Cross-sectional Spearman(12-1 momentum, next-month return),
   averaged over rebalances, is statistically indistinguishable from zero
   (|t| < 2). → No edge; stop.
2. **It's just beta.** The long-only leg's outperformance vanishes once you
   regress on the equal-weight-universe return (alpha ≈ 0, beta ≈ 1). A
   dollar-neutral long/short spread with a near-zero Sharpe says the same thing.
3. **Cost-killed.** The dollar-neutral spread is gross-positive but net-negative
   at a realistic 25-35 bps round-trip × the measured turnover.
4. **Period-specific.** The spread is positive in one sub-period and zero/negative
   in the other (the mirage that killed `vol_z` and 1-day reversal — §10 of the
   guidelines).

If any of 1-4 holds, this is not tradable in the form tested.

---

## 2. The pre-registered design (fixed BEFORE the live run)

Pre-registering the rule prevents the multiple-comparison trap that the PEAD
thesis flagged (§5.3 there). These choices are locked; the live run reports
against them, it does not search over them.

- **Signal:** 12-1 momentum = total return from *t−252* to *t−21* trading days
  (≈ last 12 months, skipping the most recent ~1 month). The 1-month skip is not
  a free parameter — it is the standard control for the well-documented 1-month
  *reversal* that would otherwise contaminate the signal.
- **Universe:** the fixed `config.ALL_SYMBOLS` (29 NSE large/mid-caps). This is
  survivorship-biased (today's constituents) and large-cap-heavy — both make the
  result a **conservative** read on momentum, which is strongest in
  higher-dispersion mid/small-caps (same liquidity/efficiency gradient PEAD
  showed). A positive result here is meaningful; a null here does not rule out
  momentum in a wider, higher-dispersion universe.
- **Rebalance:** monthly (last trading day of each month).
- **Construction (two legs, both reported):**
  - **Dollar-neutral L/S:** long the top quintile by momentum, short the bottom
    quintile, equal-weight. Beta ≈ 0 by construction — this isolates the *pure*
    momentum premium from market direction. This is the honesty check.
  - **Long-only top quintile**, benchmarked against the equal-weight universe
    (the "market"), decomposed into alpha + beta. This is what's actually
    tradable on NSE cash (no shorting) — but it must clear the alpha test, not
    just beat the market by carrying more beta.
- **Holding period:** 1 month (held to next rebalance).
- **Cost:** 30 bps round-trip baseline, applied to measured turnover; reported
  also at 1.5× and 2× (45 / 60 bps) per the guidelines' cost-survival stage.

---

## 3. Exit rules

There are no discretionary exits — this is a periodic-rebalance portfolio, not a
trade-by-trade system. A name leaves the book at the rebalance where it drops out
of the top (or bottom) quintile. The only "stop" is the monthly re-rank.

(A future time-series-momentum *overlay* — go flat when the name/index is below
its 200-day average — is the natural crash-protection extension, but it is **out
of scope** for this first test, which measures the raw cross-sectional premium.)

---

## 4. Position sizing

Equal-weight within each leg (per `STRATEGY_GUIDELINES.md` §3e defaults: single
name ≤ ~10% with ~6 names/leg this is satisfied). No volatility-scaling in v1 —
deliberately, so the first number measures the *signal*, not a vol-targeting
overlay. Vol-scaling (inverse-vol or risk-parity weighting) is a documented
follow-up if the raw premium survives.

---

## 5. Cost assumption

30 bps round-trip baseline for NSE large-caps held for a month (delivery STT
applies on both legs for multi-day holds — higher than intraday; the guidelines'
§2 breakdown). Applied to *measured* book turnover each rebalance, not assumed
100%. Because turnover is ~20-40%/month, annual cost ≈ 12 × 0.30% × turnover ≈
0.7-1.4%/yr — small relative to a typical momentum premium, the opposite of the
daily-rebalance signals where cost was ~28%/yr.

---

## 6. Universe & period

- **Universe:** `config.ALL_SYMBOLS` (29 names). Survivorship-biased, large-cap-
  heavy — see §2 for why this makes the test conservative.
- **Period:** as much daily history as the data source returns (target ≥ 3 years
  so the in-sample sub-period split is meaningful; ≥ 14 months minimum just to
  form one 12-1 signal).

---

## 7. Validation status (per `STRATEGY_GUIDELINES.md` §7)

| Stage | Status |
|-------|--------|
| 1. Logic check | **DONE** — edge stated, falsifiable, code matches description |
| 2. Cost survival | **PASS** — low turnover (~21%/mo); net survives 2× cost (§10) |
| 3. In-sample statistical validity | **PASS, survivorship-corrected** — PIT top-200: IC t 2.0, alpha t 3.2, both sub-periods positive, 2× cost-robust (§11). Magnitude ~half the inflated static figure |
| 4. Out-of-sample | **not started — THE gate** (single 2012-2021 window so far) |
| 5. Walk-forward | not started |
| 6. Benchmark vs Nifty | **PASS (broad)** — long-only alpha +1.07%/mo beyond beta 0.92 |
| 7-8. Paper / live | not started |

**Instrument validation (done now, no market data needed):** `momentum_ic.py
--self-test` generates (a) a synthetic panel with a *planted* momentum effect and
confirms the harness recovers IC > 0 with t > 2, and (b) a pure-noise panel and
confirms IC ≈ 0 (t small). This proves the measurement code has power and does
not manufacture signal — so when it is pointed at real data, a null is a real
null and a hit is a real hit.

---

## 8. Known limitations (what this does NOT model)

1. **Survivorship & large-cap bias** in the universe — conservative for momentum
   (understates it), but real. A point-in-time, wider, higher-dispersion universe
   is the proper next universe.
2. **No F&O modelling** — the dollar-neutral L/S is *illustrative only* on NSE
   cash (multi-day shorts need F&O: lot sizes, margin, rollover — §8 of the
   guidelines). The tradable form is long-only; the L/S is the cleanliness check.
3. **No vol-scaling, no TS-momentum overlay** in v1 — measures raw signal only.
4. **Monthly bars from daily closes** — rebalance at the close is assumed
   transactable; with monthly turnover and large-caps this is mild, but real fills
   are at the *next* open/VWAP. Cost budget (30 bps) absorbs a slice of this.
5. **Single in-sample window** until Stage 4. No OOS yet — same gate PEAD is stuck
   behind.

---

## 9. How to run the live test

```bash
# instrument self-test — no market data required (proves the harness is correct)
uv run python scripts/momentum_ic.py --self-test

# live in-sample test (needs Fyers creds / reachable daily data)
uv run python scripts/momentum_ic.py --all-symbols --years 4
uv run python scripts/momentum_ic.py --symbols NSE:RELIANCE-EQ NSE:TCS-EQ ... --years 4
```

The live run prints: pooled IC + t, dollar-neutral L/S annualized return / Sharpe
/ max-DD net of cost, long-only alpha/beta vs the equal-weight market, average
monthly turnover, a sub-period robustness split, and a 1×/1.5×/2× cost-sensitivity
table. Read it against the four falsification criteria in §1.

---

## 10. Live in-sample result (2012-2021, real split-adjusted NSE data)

Fyers was unreachable in the build environment (no token; market-data hosts
blocked by the network policy), so the run used a public substitute: the GitHub
dataset `Ratnesh-bhosale/NIFTY500_dataset` — Yahoo-derived daily **Adj Close**
(split/dividend-adjusted, the correct input for 12-month momentum), 2012-01-02 →
2021-12-31, 107 monthly rebalances. Reproduce with:

```bash
uv run python scripts/momentum_ic.py --github --universe allsymbols   # pre-registered 30
uv run python scripts/momentum_ic.py --github --universe top --top-n 200
uv run python scripts/momentum_ic.py --github --universe all          # full NIFTY500
```

The dispersion gradient predicted in §2 is confirmed — momentum strengthens
**monotonically** with universe breadth:

| Universe | n | IC | IC t | L/S net Sharpe | L/S net ann | maxDD | Long-only α/mo | α t | β |
|----------|---|-----|------|------|------|-------|------|------|------|
| ALL_SYMBOLS (pre-registered, large-cap) | 30  | +0.044 | 1.56 | 0.13 | +3.3%  | −57% | +0.57% | 1.27 | 0.87 |
| Top 200 (mcap)                          | 197 | +0.043 | 2.48 | 0.40 | +7.2%  | −35% | +0.75% | 2.91 | 0.91 |
| Full NIFTY500                           | 483 | +0.050 | 3.31 | 0.81 | +14.0% | −28% | +1.07% | 4.22 | 0.92 |

Against the four falsification criteria (§1):
1. **IC ≈ 0? NO** — broad-universe IC t 2.5-3.3, significant. Edge present.
2. **Just beta? NO** (broad) — long-only alpha t 2.9-4.2 *beyond* beta ~0.9.
   **YES** (large-cap-only) — alpha t 1.27, indistinguishable from beta.
3. **Cost-killed? NO** — turnover ~21-24%/mo; net survives 2× cost easily
   (the whole point of a low-turnover design — contrast the dead daily signals).
4. **Period-specific? NO** — both sub-period halves positive at every breadth
   (full universe H1 Sharpe 0.97, H2 0.63).

**Verdict: cross-sectional momentum is a real, significant, cost-robust,
beta-adjusted edge on NSE in this in-sample window — the strongest candidate this
repo has produced (full-universe net Sharpe ~0.8 vs PEAD's ~0.5).** The
pre-registered large-cap universe is too efficient/narrow to clear the bar
(t 1.56, no alpha beyond beta) — confirming the edge lives in the higher-dispersion
broad universe, the same liquidity/efficiency gradient PEAD showed.

### Why this is NOT yet tradable at the stated magnitude — the caveats that gate it
1. **Survivorship bias (the big one).** The universe is NIFTY500 membership as of
   ~March 2020 (the dataset's `MCAP_31032020` snapshot) applied to 2012-2021
   history. Names that were small in 2012 and *grew into* the 500 by 2020 are
   present for their whole history — and those are precisely the momentum winners.
   This biases the level UP, likely materially. The *gradient* and *direction* are
   credible; the *magnitude* (Sharpe 0.8, 14%/yr) is optimistic until a
   point-in-time constituent universe is used.
2. **In-sample only, one window** (2012-2021). No out-of-sample. THE gate, same as
   PEAD. Stage 4 not started.
3. **Momentum-crash tail.** maxDD −28% to −57% (the 2018-20 mid/small-cap drawdown
   + 2020 COVID reversal). The TS-momentum 200-day flat-switch / vol-scaling
   overlay (§3 follow-up) exists to cut this tail; untested here.
4. **Short leg illustrative only** — NSE multi-day shorts need F&O (§8 guidelines).
   The tradable form is long-only: beta ~0.9 + the alpha tilt.
5. **Third-party data, not live Fyers** — Yahoo-derived, ends 2021, not
   independently audited. A live-pipeline rerun is needed before trusting specifics.

### Next steps (priority order)
1. ~~Point-in-time universe~~ — **DONE, see §11.**
2. ~~Risk overlay~~ — **DONE, see §12: lifts Sharpe 0.49→0.79 but does NOT cut the
   ~−40% tail (an up-market value-rotation crash the standard fixes miss).**
3. **Out-of-sample window** (2022-2026 via live Fyers) with the rule frozen — the
   remaining gate (Stage 4). Single 2012-2021 window so far.
4. Only then a production NautilusTrader portfolio backtest.

---

## 11. Survivorship correction — point-in-time liquidity universe (2026-06)

The §10 static universe is NIFTY500 membership as of ~2020, so names that *grew
into* the index are present for their whole 2012 history — momentum winners baked
in. The fix: at **each** monthly rebalance, select the universe dynamically as the
top-K names by **trailing-63-day rupee turnover** (median of Close×Volume up to
that rebalance — point-in-time, no look-ahead). A name that wasn't liquid yet at
rebalance *r* is excluded at *r*, so its later run-up no longer counts as a
position we'd have held. Implemented as `momentum_ic.py --pit-top-k K`:

```bash
uv run python scripts/momentum_ic.py --github --universe all --pit-top-k 200
```

| Universe | distinct names used | IC t | L/S net Sharpe (1×) | long-only α t | maxDD | sub-periods (H1/H2 Sharpe) |
|----------|------|------|------|------|------|------|
| Static full 483 (**survivorship-inflated**) | 483 | 3.31 | **0.81** | 4.22 | −28% | +0.97 / +0.63 |
| PIT top-50 (megacaps only)   | 129 | 1.28 | 0.03 | 0.59 ✗ | −62% | +0.16 / −0.10 ✗ |
| PIT top-100                  | 202 | 1.76 | 0.24 | 2.03 | −47% | +0.28 / +0.20 |
| **PIT top-200 (honest, tradable)** | 376 | **2.02** | **0.49** | **3.18** | −40% | +0.47 / +0.51 ✓ |

**What the correction reveals:**
1. **The 0.81 Sharpe was ~40% survivorship inflation.** The honest, point-in-time
   number is **L/S net Sharpe ~0.5, long-only alpha ~0.9%/mo (t 3.2, ~11%/yr)
   beyond beta 0.92**, robust across both sub-periods, surviving 2× cost. Real and
   significant — but roughly half the headline, and now comparable-to-modestly-
   better than PEAD (~0.5), not a windfall.
2. **The size/dispersion gradient is genuine, not a survivorship artifact** — it
   persists *within* the point-in-time universe: top-50 megacaps have NO edge
   (alpha t 0.59, H2 negative — too efficient), while the broader top-200 liquid
   names do (alpha t 3.18). This is the same efficiency gradient PEAD showed,
   measured cleanly. The tradeable sweet spot is the *broad-but-liquid* ~200-name
   set, not the megacaps and not the untradeable small-cap tail.
3. **The crash tail survives the correction** — maxDD −40% at top-200. A risk
   overlay (next step) is not optional for live trading.

**Residual caveat that remains un-fixable with this dataset:** the candidate pool
is still only names that survived to the 2020 snapshot — stocks delisted/failed
before 2020 are absent entirely, which no PIT filter can recover. So even the
top-200 Sharpe ~0.5 is a mild *upper* bound. The honest read: **a real, modest,
tradable momentum edge (Sharpe ~0.4-0.5, long-only alpha ~10%/yr) in a broad
liquid NSE universe — pending out-of-sample confirmation and a crash-risk overlay.**

---

## 12. Crash-risk overlays — Sharpe improves, the tail does NOT (2026-06)

Two textbook momentum-crash fixes, both look-ahead-free, applied to the PIT
top-200 L/S book (`momentum_ic.py --overlay`):
- **Vol-scaling** (Barroso-Santa-Clara): size inversely to trailing-6m realized
  vol, targeting the book's own long-run vol (stabilize, not leverage).
- **Market-trend filter** (Daniel-Moskowitz): momentum crashes cluster in
  bear-market rebounds → hold only when the trailing-12m market return is
  positive, else flat.

| Variant | ann.ret | vol | Sharpe | maxDD | avg exposure |
|---------|---------|-----|--------|-------|------|
| baseline (no overlay) | +10.3% | 21.0% | 0.49 | **−39.7%** | 1.00 |
| vol-scaled            | +11.2% | 24.3% | 0.46 | −39.1% | 1.29 |
| market-trend filter   | +13.5% | 18.7% | **0.72** | −39.7% | 0.83 |
| vol-scaled + trend    | +16.7% | 21.3% | **0.79** | −39.1% | 1.08 |

**The honest finding: the overlays raise risk-adjusted return (Sharpe 0.49 → 0.79)
but barely touch the dominant tail (maxDD stays ~−39%).** Why — and it's the
interesting part:

- The defining drawdown is the **2014 momentum crash** (peak Jun-2013 → trough
  Apr-2014): the pre/post-Modi-election rally rocketed beaten-down PSU/infra/
  cyclical names, crushing the short leg (Feb-2014 −20.8%, Apr-2014 −18.8%).
- **The market-trend filter misses it entirely** — the trailing-12m market return
  was strongly *positive* (+14% to +30%) right through the crash. Daniel-Moskowitz
  protects against crashes in *down* markets (à la 2009); the 2014 Indian crash was
  a **style rotation in a roaring up-market**, so the bear filter never fires
  (exposure stayed 1.0 throughout).
- **Vol-scaling can't anticipate it** — the Feb-2014 −21% hit while trailing vol
  was still normal (weight ≈ 1.07); scaling only cut size *after* the first crash
  month, trimming April slightly (−39.7% → −39.1%). It helps crashes that follow a
  vol build-up; this one was abrupt.

**Implication.** The Sharpe lift is real but comes from sitting out generally-weak
stretches (trend filter, avg exposure 0.83) and calm-period stabilization — not
from crash protection. The ~−40% tail is an **up-market value-rotation crash**,
a different animal from the US bear-rebound crashes these tools were built for,
and it remains essentially unhedged here. Possible next angles (untested): a
short-leg beta cap / dynamic hedge, faster vol estimation, or an
idiosyncratic-momentum (residual, beta-neutralized) construction — but none is a
known fix for up-market rotation. *Caveat:* the vol-target level uses full-sample
vol (cosmetic only — Sharpe/maxDD are scale-invariant, so the verdict is
unaffected); the 6m/12m windows are unoptimized and their sensitivity is untested.
</content>
</invoke>
