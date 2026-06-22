"""Run a strategy in PAPER mode (stage >= backtest).

Paper mode is simulated execution with live/cached market data; no broker orders.
"""
from __future__ import annotations

import importlib
import sys

from core.manifest import Stage
from runners._common import load_manifest, require_not_halted, require_stage


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: python -m runners.paper <strategy> [args...]")
    name, rest = sys.argv[1], sys.argv[2:]
    manifest = load_manifest(name)
    require_stage(manifest, Stage.backtest)
    require_not_halted(manifest)
    try:
        mod = importlib.import_module(f"strategies.{name}.paper")
    except ModuleNotFoundError:
        sys.exit(f"strategies/{name}/paper.py not found.")
    mod.main(rest)


if __name__ == "__main__":
    main()
