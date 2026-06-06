# Short-term reversal — STATUS: DROPPED (2026-06)

## Hypothesis

Short-term losers bounce, winners mean-revert: long recent losers / short
recent winners cross-sectionally, daily rebalance.

## Why it was dropped

- The in-sample lead **weakened with more data and a wider universe** — the
  signature of a mirage, not an edge (RESEARCH_BACKLOG.md "leads that weaken
  were mirages").
- Like every daily-rebalance L/S tested, the small gross edge (~0–20%/yr)
  was eaten by ~28%/yr round-trip cost at 15 bps.

## Re-entry condition

None in simple-OHLCV form. Requires richer data (microstructure, flow) or a
structurally lower-turnover design.
