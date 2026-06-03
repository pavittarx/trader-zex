# Strategy Thesis — Cross-Sectional Momentum (Trend-Following), NSE

Status: **THESIS + INSTRUMENT BUILT, LIVE TEST PENDING DATA (2026-06).**
Stage 1 (logic) written; the test harness (`scripts/momentum_ic.py`) is built and
self-test-verified (recovers a planted signal, stays flat on noise). The live
in-sample verdict is gated on a run with reachable daily data (Fyers creds or an
equivalent source) — the build environment had neither a Fyers token nor egress
to any market-data host. Documented per `STRATEGY_GUIDELINES.md` §9.

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
| 2. Cost survival | pending live run (harness computes 1×/1.5×/2×) |
| 3. In-sample statistical validity | pending live run (harness computes IC, t, sub-period split) |
| 4. Out-of-sample | not started |
| 5. Walk-forward | not started |
| 6. Benchmark vs Nifty | partial — long-only leg is decomposed vs equal-weight universe |
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
</content>
</invoke>
