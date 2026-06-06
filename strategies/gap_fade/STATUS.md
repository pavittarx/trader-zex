# Gap fade — STATUS: DROPPED (2026-06)

## Hypothesis

Overnight gaps overshoot (retail/news overreaction at the open); fading the
gap — long big gap-downs, short big gap-ups, hold open→close — captures the
intraday reversion.

## Why it was dropped

- The daily-bar IC looked real, but the **intraday timing check killed it**:
  the reversion accrues before a realistic entry (the move happens in the
  first minutes / at unreachable auction prices). See GAP_FADE_THESIS.md §8.
- What remained net of 15–25 bps daily round-trip cost was ≤ 0: a
  daily-rebalanced cross-sectional L/S is the highest-turnover design
  possible (~28%/yr cost at 15 bps).

## Lesson (encoded in the pipeline)

A strong daily-bar IC proves nothing tradable. Always run the intraday
timing check (`gap_fade_intraday.py` pattern, now in the shared research
harness) BEFORE building a backtest. This stage-gate exists because of this
strategy.

## Re-entry condition

None as daily-rebalance L/S. Only a low-turnover, selectivity-based variant
with an execution edge (limit-order spread capture) would justify a new
hypothesis folder.
