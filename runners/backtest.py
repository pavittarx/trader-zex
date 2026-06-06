"""Run a strategy's NautilusTrader backtest (stage >= backtest).

    python -m runners.backtest <strategy> [strategy-specific args...]

Delegates to strategies/<name>/backtest.py:main(argv) by convention — each
strategy owns its data prep and engine wiring while sharing core.backtest
machinery (data_loader, instruments, engine, metrics).
"""
from __future__ import annotations

import importlib
import sys

from core.manifest import Stage
from runners._common import load_manifest, require_stage


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: python -m runners.backtest <strategy> [args...]")
    name, rest = sys.argv[1], sys.argv[2:]
    manifest = load_manifest(name)
    require_stage(manifest, Stage.backtest)
    try:
        mod = importlib.import_module(f"strategies.{name}.backtest")
    except ModuleNotFoundError:
        sys.exit(f"strategies/{name}/backtest.py not found — the strategy is "
                 f"stage={manifest.stage.name} but has no backtest entry point.")
    mod.main(rest)


if __name__ == "__main__":
    main()
