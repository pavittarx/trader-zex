# Intraday/Daily Research Backlog

Candidate edge hypotheses for NSE equities, intraday-to-daily horizon (no
overnight-only holds). Each follows the discipline from `STRATEGY_GUIDELINES.md`:
state the edge + who's wrong, then test IC cheaply, then validate entry/exit
**timing on intraday bars** before trusting anything (the gap-fade lesson —
`GAP_FADE_THESIS.md` §8).

Status: ACTIVE — PEAD candidate under validation (2026-06).
> **UPDATE (2026-06): first live candidate found — PEAD.** Earnings-reaction
> drift survived scaling (44→186 events, t≈2.5) where price/volume leads did
> not. Low-turnover, cost math works. See `PEAD_THESIS.md`. Needs OOS.

Prior parked items below. Tools to reuse live in `scripts/`:
`feature_ic.py`, `intraday_edge.py`, `gap_fade_test.py`, `gap_fade_intraday.py`,
`breakout_test.py`.

> **Sweep conclusion (2026-06):** six signal families tested (HMM-confluence,
> momentum, reversal, gap-fade, gap-continuation, compression-breakout) — none
> tradable. The **simple OHLCV signal space on NSE equities is empty of retail
> edge**: signals are either ~0 gross, evaporate out-of-sample, accrue at
> unreachable prices, or have a real gross edge that daily-rebalance cost eats.
> A step-change is required to progress — richer data (microstructure / options
> flow / fundamentals / events), better execution (capture spread via limit
> orders), or a different problem entirely. Further simple-OHLCV variants are
> expected to fail and are not worth testing.

> **Hard rule learned:** a strong *daily-bar* IC proves nothing tradable. Always
> confirm the return is reachable at a price/time you can actually transact, and
> net of realistic round-trip cost (~12–25 bps intraday for liquid names). Most
> intraday effects die on turnover cost — design for low turnover or selectivity.

> **The binding constraint (2026-06, after testing 4 signal families):** every
> cross-sectional, rebalance-every-day intraday long/short we tested (reversal,
> gap-fade, gap-continuation) had only a small gross edge (~0–20%/yr) that was
> eaten by daily round-trip cost (~28%/yr at 15 bps). Continuation: gross ≈ +20%,
> break-even cost ≈ **8 bps/day**, realistic cost 12–25 bps → net −8.5%. The
> problem is **structural, not signal discovery**: daily-rebalanced L/S is the
> highest-turnover design possible. Prioritise future ideas by TURNOVER —
> selective, few-trades-per-day, high-per-trade-edge setups — not by signal
> strength alone. Re-prioritised below.

---

## 1. Intraday continuation / opening-range breakout — TESTED, cost-killed
**Edge:** information diffuses slowly and momentum traders pile in after the
open, so gaps continue intraday.
**Result (2026-06, broad universe, 6mo, realistic 9:30 entry, 15 bps):** gross
edge is real and positive (~+20%/yr) — gaps DO continue — but net −8.5% (t −0.42)
after daily-rebalance cost. Break-even ≈ 8 bps/day; no margin vs 12–25 bps real.
**Verdict:** as a daily-rebalanced cross-sectional L/S, cost-killed like the
others. Only worth revisiting in a LOW-TURNOVER form (e.g. only the strongest
breakouts, held longer / sized larger), not every-name-every-day.

**Execution-lever follow-up (`continuation_limit.py`, broad univ, 6mo, |gap|>1%):**
We attacked the cost wall directly — limit-order entry vs market, with honest
adverse-selection accounting (a passive limit counts as filled only if price
trades through it). Result: limit entry DOES help (+2.2 vs −1.3 bps/trade vs
market) and fill rate stays high (89–99% — adverse selection is mild). BUT the
net edge is **+2.2 bps/trade, t +0.4, win 50% — statistically zero.** The
execution lever is real; the signal is simply too thin to clear it. Reaching
t>2 would need ~25× the data. **Continuation is exhausted, including its best
execution form.**

## 2. Intraday VWAP reversion
**Edge:** transient order-flow imbalances push price away from VWAP; it reverts
as liquidity replenishes intraday.
**Who's wrong:** impatient market-order flow paying for immediacy.
**Test:** deviation from rolling intraday VWAP at time T predicts reversion to
VWAP by a later bar. Needs 1-min bars + volume (available via Fyers resample).
Turnover is high → cost is the gate.

## 3. Closing-session pressure
**Edge:** index funds / MFs rebalance into the NSE closing session, creating
semi-predictable directional pressure in the last 30–60 min.
**Who's wrong:** mandated, price-insensitive rebalance flow.
**Test:** does the late-session (e.g. 14:30→15:00) move or imbalance predict the
close / next-open? Lower turnover than #2.

## 4. Volatility-compression breakout — TESTED, no gross edge
**Edge (hypothesised):** range contraction precedes a directional expansion.
**Result (2026-06, broad universe, 6mo, NR7 → break prior day high/low → hold to
close, 15 bps):** net −15.2 bps/trade (t −2.24), win 43%, ~36 trades/sym/yr.
Gross ≈ 0 — breakouts *fail* (revert) more than they follow through to the
close. Not a cost problem; the premise is wrong for this universe/period.
**Possible (unlikely) refinement:** trailing-stop exit instead of hold-to-close,
or volume-confirmed breakouts — but the ~0 gross premise is weak.

## 5. Index-relative intraday reversion (residual)
**Edge:** a single stock decouples from its index intraday on idiosyncratic flow,
then reconverges.
**Test:** intraday residual = stock return − β·NIFTY return; does the residual at
time T revert by close? Market-neutral by construction.

---

## How to work an item (cheap → expensive)
1. **IC screen** on daily/derived features (`feature_ic.py`) — kill fast if ~0.
2. **Intraday timing check** (`gap_fade_intraday.py` pattern) — confirm the
   return is reachable at realistic entry/exit, net of cost. This is where
   gap-fade died; do it *before* building anything.
3. **Wider universe + out-of-sample window** — leads that strengthen with more
   data survive; leads that weaken (vol_z, reversal) were mirages.
4. Only then: a production backtest (NautilusTrader `backtest/`, cost reporting
   already fixed) and the GUIDELINES §7 validation hierarchy.
