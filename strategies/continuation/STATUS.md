# Gap continuation / opening-range breakout — STATUS: DROPPED (2026-06)

## Hypothesis

Information diffuses slowly; momentum flow piles in after the open, so
overnight gaps CONTINUE intraday (the opposite of gap-fade).

## Why it was dropped

The most instructive kill of the sweep — the edge was real, the economics
weren't:
- **Gross edge confirmed**: ~+20%/yr — gaps do continue.
- **Cost-killed**: net −8.5%/yr (t −0.42) at realistic 12–25 bps; break-even
  ≈ 8 bps/day. Daily-rebalance L/S turnover is structurally fatal.
- **Execution-lever exhausted** (`continuation_limit.py`): limit-order entry
  with honest adverse-selection accounting DOES help (+2.2 vs −1.3 bps/trade,
  89–99% fill) — but +2.2 bps/trade, t +0.4, win 50% is statistically zero.
  Reaching t>2 would need ~25× the data. Continuation is exhausted,
  including its best execution form.

## Lesson (encoded in the pipeline)

Prioritize hypotheses by TURNOVER, not signal strength. A real gross edge
with daily-rebalance turnover is still a losing strategy.

## Re-entry condition

Only a low-turnover form: strongest breakouts only, held longer, sized
larger — a different hypothesis, new folder.
