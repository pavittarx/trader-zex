"""HMM-confluence archived backtest entry point.

Delegates to the existing portfolio backtest CLI (same flags: --symbols,
--all-symbols, --date-from/--date-to, --allow-shorts, --walk-forward, ...).
"""
from __future__ import annotations


def main(argv: list[str] | None = None) -> None:
    import sys
    from core.backtest.__main__ import main as backtest_main
    sys.argv = ["backtest"] + list(argv or [])
    backtest_main()
