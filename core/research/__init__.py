"""core.research — shared vectorized research harness.

The cheap stages of the pipeline (triage, vectorized tests) before any
NautilusTrader backtest. One implementation of data fetching, cost models,
stats, and event-study primitives — strategy research scripts import these
instead of copy-pasting (the pre-2026-06 scripts each carried their own
fetch_daily/stats_line; a bug had 8 places to live).
"""
