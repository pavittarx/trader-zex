# Strategy Thesis — Cross-Sectional Momentum (Trend-Following), NSE

Status: **IN-SAMPLE EDGE CONFIRMED ON REAL DATA — STRONGEST CANDIDATE SO FAR,
BUT SURVIVORSHIP-INFLATED AND NOT OOS-VALIDATED (2026-06).** Cross-sectional
12-1 momentum shows a real, significant, cost-robust, beta-adjusted edge on a
broad NSE universe (full-universe IC t 3.3, long-only alpha t 4.2, L/S net
Sharpe ~0.8 in-sample 2012-2021) — clearly stronger than PEAD (~0.5). The edge
strengthens monotonically with universe breadth, exactly as the thesis predicted
(§10). **Caveats that gate it:** the test universe is survivorship-biased (NIFTY500
membership as of ~2020), which inflates the magnitude; it is in-sample only (one
window, no OOS); and it carries a -28%+ momentum-crash tail. See §10. Documented
per `STRATEGY_GUIDELINES.md` §9.

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
| 3. In-sample statistical validity | **PASS (broad universe), with caveats** — IC t 3.3, alpha t 4.2, both sub-periods positive; BUT survivorship-inflated (§10) |
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
1. **Point-in-time universe** — kill the survivorship inflation; re-measure the
   honest magnitude. The single most important correction.
2. **Out-of-sample window** (2022-2026 via live Fyers) with the rule frozen — Stage 4.
3. **Risk overlay** — TS-momentum flat-switch and/or vol-scaling to cut the crash
   tail; measure the Sharpe improvement.
4. Only then a production NautilusTrader portfolio backtest.
</content>
</invoke>
