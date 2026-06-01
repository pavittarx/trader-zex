# Strategy Thesis — Intraday Gap Fade (NSE equities)

Status: **REJECTED (2026-06)** — the daily-bar edge does not survive realistic
intraday fills. See §8. Kept as a documented negative result and a lesson in
fill realism. Documented per `STRATEGY_GUIDELINES.md` §9. Discovered after the
HMM-confluence strategy was retired for having no edge (see GUIDELINES §10).

> **TL;DR:** strong daily-bar IC (t −6.69), but the fade occurs *inside the
> opening auction* (9:15 print), which is unreachable. Realistic entry at 9:30
> is significantly negative (t −3.1 to −3.7) — the gap then continues, not
> reverts. The +64% "gross" was a fill-realism artifact.

---

## 1. Edge hypothesis (the one sentence)

> The opening auction over-reacts to overnight order flow and news, so a stock
> that gaps far from yesterday's close partially reverts over the session — and
> we are paid to provide liquidity to that over-reaction.

**Who is on the other side, and why are they wrong?** Overnight retail and
momentum order flow concentrates at the open auction, pushing the open price
past fair value. We take the other side and hold until the over-reaction
decays during continuous trading. The effect is structural (auction
microstructure + behavioural), not a fitted pattern.

**Falsification test:** if the overnight gap has no negative cross-sectional
correlation with the same-day open→close return, the hypothesis is dead.

---

## 2. Evidence (point-in-time, no look-ahead)

Daily OHLC, 33 NSE large/mid-caps, 2025-06-01 → 2026-05-31 (246 days).
Gap is known at the open; the intraday return is realised after — clean.

| Test | Result | Significance |
|------|--------|--------------|
| Gap → intraday-return cross-sectional IC | **−0.095** | **t = −6.69** |
| Long-5 gap-downs / short-5 gap-ups, open→close, gross | **+63.8% / yr** | t = +2.78 |
| Overnight (close→open) basket return | +22.4% / yr | t = +2.09 |
| Intraday (open→close) basket return | −14.1% / yr | t = −1.40 |

The signal is strong, significant, and stable over a full year — unlike the
momentum and short-term-reversal leads, which evaporated out-of-sample.

**The catch — cost (round-trip per day, every day):**

| Round-trip cost | Net annualised (long5/short5) |
|---|---|
| 12 bps (liquid, discount broker) | ≈ +25% |
| 15 bps | ≈ +11% |
| **~19 bps (break-even)** | **≈ 0%** |
| 20 bps | −1% |

Gross daily edge ≈ 19 bps; break-even cost ≈ 19 bps. **Tradability hinges
entirely on real execution cost being comfortably below ~17 bps.**

---

## 3. Proposed rules (to be validated on intraday data)

- **Universe:** liquid NSE large/mid-caps (tight spreads — cost is the binding
  constraint). Avoid thin names where spread alone exceeds the edge.
- **Signal:** at/after the open, `gap = open / prev_close − 1` for each name.
- **Entry:** SHORT the largest gap-ups, LONG the largest gap-downs (top/bottom-k,
  or gap-magnitude weighted). Dollar-neutral long/short.
- **Exit:** flatten all before the close (intraday only — MIS-compatible, no
  overnight short needed).
- **Sizing:** equal risk per leg; cap per-name notional and volume participation
  (GUIDELINES §3e, §5). Weight by gap size only if intraday tests support it.

## 4. Open questions the intraday backtest must answer

1. **Real round-trip cost** — the decisive number. Below ~17 bps → tradable.
2. **Fill realism** — you cannot assume a fill at the open print. Model the
   opening-auction / first-minutes spread; test entry 5–15 min after open.
3. **Exit timing** — flatten at close vs. 15 min before; does the fade complete?
4. **Selectivity vs. turnover** — every-day top-k has the best stats but most
   cost; large-gap-only (|gap|>3%) is net-positive but rare (~37 days/yr).
   Find the gap threshold that maximises net Sharpe.
5. **Capacity** — gap-up shorts need borrow/MIS availability; confirm per name.

## 5. How to test (next phase)

1. Pull 1-min bars for the universe (Fyers `get_history("1", …)`, resample).
2. Build an intraday gap-fade backtest in `backtest/` (NautilusTrader; the cost
   reporting is already fixed — GUIDELINES §10). Model realistic fills and the
   *actual* cost structure, not a flat assumption.
3. Validate via the GUIDELINES §7 hierarchy: cost survival → in-sample → walk
   forward → benchmark → paper. The gap-fade IC already clears the §4c bar; the
   gate now is §2 (cost) and §3c (fill realism).

## 6. Known limitations / risks

- **Cost-marginal:** a small adverse move in real cost or slippage flips it
  negative. Not a high-margin edge — execution quality *is* the strategy.
- **Crowded-ness:** gap reversion is well known; edge may compress over time.
- **Short side:** intraday short relies on MIS availability and broker cut-offs;
  some names may be restricted on volatile gap days (when the edge is largest).
- **Single year, daily-bar proxy:** evidence uses daily open as the entry price.
  Intraday data may show worse fills than the open print implies.

## 8. Intraday validation result — REJECTION (2026-06)

Tested on real 15-min bars via `scripts/gap_fade_intraday.py`, which models
entry/exit timing instead of the daily open-print proxy.

Broad universe (28 large/mid-caps), 6 months (2025-12 → 2026-05), 120 days,
k=5/leg, 15 bps round-trip:

| Entry | Exit | Net ann. | t | Sharpe |
|-------|------|----------|---|--------|
| open(auction) — control | close | −23.1% | −0.82 | −1.19 |
| **open (9:30)** | close | **−48.8%** | **−3.15** | −4.56 |
| open+15m | close | −49.1% | −3.33 | −4.83 |
| open+30m | close | −46.3% | −3.47 | −5.03 |

Confirmed on a separate 12-large-cap / 90-day slice (realistic entry ~−48%,
auction control ~−20%). The auction→9:30 gap of ~25%/yr is consistent across
both runs.

**Why it failed:**
1. **The fade is an opening-auction phenomenon.** The reversion happens in the
   9:15 auction print → first minutes. Entering at 9:30 (the earliest realistic
   continuous-market fill) misses it; thereafter the gap *continues* (intraday
   momentum), so a fade held to the close loses. The ~25%/yr gap between the
   auction-print control and 9:30 entry is exactly this unreachable return.
2. **Costs.** Even the (unreachable) auction-print entry is net break-even to
   negative once daily round-trip costs are applied.

**The lesson (added to GUIDELINES):** a strong *daily-bar* IC says nothing about
tradability if the return accrues at a price/time you cannot transact. Always
validate the entry/exit **timing** on intraday bars before trusting a daily-bar
backtest of an intraday strategy. The +64% daily "gross" was the open-auction
print + whole-session hold — a fill-realism mirage (GUIDELINES §3c).

## 9. Reusable tools built for this

- `scripts/feature_ic.py` — per-feature information coefficient screen.
- `scripts/reversal_test.py` — long/short reversal with break-even cost.
- `scripts/intraday_edge.py` — gap-fade IC + overnight/intraday decomposition.
- `scripts/gap_fade_test.py` — cost-aware gap-fade long/short (k-based + threshold).
