# Strategy Thesis — Post-Earnings-Announcement Drift (PEAD), NSE

Status: **LIVE CANDIDATE (2026-06)** — first signal to survive a scaling test.
Promising and economically meaningful net of cost, but not yet validated
out-of-sample. Documented per `STRATEGY_GUIDELINES.md` §9.

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

## 3. Proposed rule (to validate, not yet trade)
- **Signal:** on each earnings reaction day (t+1 after announcement), sign of the
  reaction-day return.
- **Entry:** at the reaction-day close — long if reaction up, short if down.
- **Hold:** ~20 trading days (the form with the best net margin), or test a
  shorter 1-day variant.
- **Universe:** liquid large/mid-caps. Shorts via MIS/F&O constraints apply.
- **Sizing:** equal-risk per event; standard caps (GUIDELINES §3e, §5).

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
