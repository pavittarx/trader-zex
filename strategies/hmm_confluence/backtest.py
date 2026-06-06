"""HMM-confluence backtest entry point — `python -m runners.backtest hmm_confluence`.

Delegates to the existing portfolio backtest CLI (same flags: --symbols,
--all-symbols, --date-from/--date-to, --allow-shorts, --walk-forward, ...).
"""
from __future__ import annotations


def main(argv: list[str] | None = None) -> None:
    import sys
    from core.backtest.__main__ import main as backtest_main
    sys.argv = ["backtest"] + list(argv or [])
    backtest_main()
