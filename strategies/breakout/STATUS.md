# Volatility-compression breakout — STATUS: DROPPED (2026-06)

## Hypothesis

Range contraction (NR7) precedes directional expansion: enter on a break of
the prior day's high/low, hold to close. Selective (~1 day in 7) so cost per
trade is amortized — a deliberately low-turnover design.

## Why it was dropped

- **No gross edge**: net −15.2 bps/trade (t −2.24), win 43% over a broad
  universe, 6 months. Breakouts *fail* (revert) more often than they follow
  through. Not a cost problem — the premise is wrong for this universe/period
  (RESEARCH_BACKLOG.md §4).

## Re-entry condition

Weak. A trailing-stop exit or volume-confirmed variant could be tested
cheaply via the research harness, but the ~0 gross premise makes it a low
priority.
