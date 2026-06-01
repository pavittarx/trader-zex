# Strategy Thesis — Post-Earnings-Announcement Drift (PEAD), NSE

Status: **MARGINAL CANDIDATE (2026-06)** — real but universe-dependent. The
per-event drift is genuine and survived scaling/sub-period tests, but the
portfolio Sharpe halved (1.10 → 0.51) when the universe was broadened from 47 to
90 names: PEAD concentrates in less-efficient mid/small-caps and is weak in
liquid blue-chips (matches the literature). Tradable edge lives where liquidity
is worst — a capacity/cost tradeoff. Not validated cross-regime. Documented per
`STRATEGY_GUIDELINES.md` §9.

## 1. Edge hypothesis
> Investors underreact to earnings news; a stock's earnings-day move continues
> (drifts) over the following days/weeks as the information is slowly priced in.
> *Who's wrong:* slow-to-update investors (limited attention, anchoring).
> *Why it fits us:* event-conditioned, ~4 trades/yr/stock — **low turnover**, so
> the round-trip cost that killed the price/volume signals is a small fraction
> of the per-event move.

## 2. Evidence (point-in-time, corrected alignment)
Data: `nsepython.nse_past_results` (announcement dates) + Fyers daily prices.
Universe 47 NSE large/mid-caps, ~2 years, **186 events**.

**Critical alignment fix:** results are announced *after-hours* on `re_create_dt`,
so the market reacts the NEXT session. The reaction day must be the first
trading day STRICTLY AFTER `re_create_dt` (verified by inspecting return/volume
spikes — they land on t+1). Using t+0 produced a spurious −0.30 reversal; the
fix flipped it to a real positive drift.

Reaction = move into the reaction day; drift_N = reaction-close → N days later.
Sign L/S = long positive-reaction events, short negative, hold N days.

| Horizon | IC | t | Sign L/S drift | t |
|---------|-----|-----|----------------|-----|
| 1 day   | +0.18 | +2.48 | +0.31% | +2.27 |
| 5 day   | +0.08 | +1.04 | +0.23% | +0.95 |
| 10 day  | +0.12 | +1.59 | +0.57% | +1.75 |
| 20 day  | +0.14 | +1.86 | **+1.17%** | **+2.48** |

Survived scaling from 44 → 186 events (1-day t held; 20-day drift emerged) —
the test that killed `vol_z` and short-term reversal (both collapsed to zero).

## 2b. Refinement (2026-06) — reaction-magnitude conditioning
Splitting the 186 events at the median |reaction| (1.95%): the drift concentrates
in LARGE-reaction events, as PEAD predicts (bigger news → more underreaction).

| Horizon | LARGE \|react\| (n=93) | SMALL \|react\| (n=93) |
|---------|----------------------|------------------------|
| 1 day   | **+0.47% (t+2.36)**  | +0.16% (t+0.83) |
| 10 day  | +0.72% (t+1.58)      | +0.43% (t+0.90) |
| 20 day  | +1.43% (t+1.94)      | +0.91% (t+1.53) |

Trading only large-reaction events ~doubles the per-trade margin (1-day LARGE
≈ +27 bps net vs ~+11 unconditioned) AND cuts turnover (half the events).

**EPS QoQ surprise (exploratory):** weak — IC +0.125 (t+1.70) at 1 day, ~0
beyond. Shallow data (~5 quarters) + seasonality make raw QoQ EPS noisy; the
price reaction already embeds the market's surprise-vs-expectations read, so it
is the better signal. A fundamental-surprise angle needs a deeper data source
(with consensus estimates).

## 3. Proposed rule (to validate, not yet trade)
- **Filter:** only act on events with |reaction| ≥ ~2% (the drift lives here).
- **Signal:** sign of the reaction-day (t+1) return.
- **Entry:** at the reaction-day close — long if reaction up, short if down.
- **Hold:** 1 day (robust core, ~+27 bps net/trade) or ~20 days (fatter
  ~+118 bps but more period-dependent — H2-driven).
- **Universe:** liquid large/mid-caps. Shorts via MIS/F&O constraints apply.
- **Sizing:** equal-risk per event; standard caps (GUIDELINES §3e, §5).

## 3b. Portfolio backtest (2026-06) — `scripts/pead_backtest.py`
Equal-weight active book (target 10 positions = full investment), |reaction|≥2%,
enter reaction-day close, hold H, exit close, 20 bps round-trip. 47 names, ~2yr,
89 trades.

| Hold | CAGR | Sharpe | maxDD | Active days |
|------|------|--------|-------|-------------|
| 1 day  | +1.1% | +0.78 | −1.1% | 10% |
| 5 day  | +0.5% | +0.21 | −2.5% | 22% |
| 20 day | **+5.2%** | **+1.10** | **−3.0%** | 36% |

**The edge survives portfolio assembly** (Sharpe ~1.1 on these 47, shallow DD,
net of cost) — but see the capacity test below: it does NOT generalize at the
same strength to a broader universe.

### Capacity test (2026-06) — scaling the universe DILUTED it
Re-ran on 90 names (added ~43 liquid blue-chips), 156 trades:

| Universe (20-day hold) | Trades | CAGR | Sharpe | maxDD |
|------------------------|--------|------|--------|-------|
| 47 names (mid-cap-heavy) | 89 | +5.2% | **+1.10** | −3.0% |
| 90 names (+ blue-chips)  | 156 | +3.1% | **+0.51** | −7.0% |

Sharpe halved, drawdown doubled. The added blue-chips have **weak PEAD** (priced
efficiently); the original 47 skewed mid-cap/volatile where PEAD is strong. This
matches the literature (drift concentrates in small/illiquid/low-coverage names)
and means the edge **does not scale by adding liquid names** — it lives where
liquidity (and thus tradability) is worst. The 47-name Sharpe 1.1 was partly a
favourable-universe artifact. Realistic assessment: a **marginal** effect
(broad-universe Sharpe ~0.5), strongest in hard-to-trade names.

## 4. Net-of-cost margin
20-day form: +1.17% gross/trade − ~15–25 bps round-trip ≈ **+95 bps/trade**.
Low turnover means cost is paid rarely and dwarfed by the move — the opposite of
the daily-rebalance signals.

## 5. Open questions / before trading
1. **Out-of-sample / more regimes** — only one ~2-yr window so far. THE gate.
2. **Data depth** — `nse_past_results` returns only ~5 quarters/symbol; a deeper
   earnings-date + estimates source is needed to validate across history and to
   add a real *surprise* measure (vs. the price-reaction proxy).
3. **Multiple-comparison** — 4 horizons tested; 1-day & 20-day significant.
   Pre-register the chosen horizon before the OOS test.
4. **Short-side feasibility** — NSE intraday/MIS limits; F&O for multi-day shorts.
5. **Build into `backtest/`** (NautilusTrader, event-driven engine, cost
   reporting fixed) for a realistic portfolio backtest once OOS-validated.

## 6. Tools
- `scripts/pead_event_ic.py` — the event-study IC harness (chunked daily fetch,
  t+1 reaction alignment).

## 8. Fundamental-surprise attempt (2026-06) — negative, instructive
Scraped deep quarterly EPS from screener.in (`scripts/screener_data.py`, ~13
quarters/symbol vs nse's 5) to test a real YoY earnings surprise
(`scripts/pead_fundamental.py`, 20 names, 160 events).

| Horizon | IC(SUE) | t | IC(reaction) | t |
|---------|---------|-----|--------------|-----|
| 1 day   | +0.020 | +0.25 | −0.134 | −1.70 |
| 5 day   | +0.054 | +0.68 | −0.234 | −3.03 |
| 20 day  | −0.073 | −0.92 | −0.133 | −1.68 |

**Verdict: free deeper data does NOT improve PEAD.**
1. **YoY EPS surprise has no drift signal** (IC≈0). Raw YoY growth is largely
   *anticipated* — a true "surprise" needs consensus ESTIMATES (actual vs.
   expected), which screener lacks. The price reaction stays the better proxy.
2. **Volume-snap dating is unreliable** — it flipped the reaction-IC negative,
   contradicting the validated nse-exact-date study (+0.18). screener has no
   clean announcement dates; snapping to the max-volume day mis-dates events.

**Implication for data spend:** the missing ingredient is consensus estimates
(paid: Trendlyne / EODHD / IBES), NOT more EPS history. Don't pursue further
free-fundamental refinements. The validated price-reaction PEAD (§2–3b) — real
but marginal, universe-dependent — remains the best form.
