"""Run a strategy in the SANDBOX environment (stage >= sandbox).

Live market data + NT SandboxExecutionClient (paper fills, zero capital).
See docs/ENVIRONMENTS.md. Refuses halted strategies.
"""
from __future__ import annotations

import importlib
import sys

from core.manifest import Stage
from runners._common import load_manifest, require_not_halted, require_stage


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: python -m runners.sandbox <strategy> [args...]")
    name, rest = sys.argv[1], sys.argv[2:]
    manifest = load_manifest(name)
    require_stage(manifest, Stage.sandbox)
    require_not_halted(manifest)
    try:
        mod = importlib.import_module(f"strategies.{name}.sandbox")
    except ModuleNotFoundError:
        sys.exit(f"strategies/{name}/sandbox.py not found. The sandbox TradingNode "
                 f"(Fyers NT data client + SandboxExecutionClient) is not built yet — "
                 f"see the milestones in strategies/{name}/STATUS.md.")
    mod.main(rest)


if __name__ == "__main__":
    main()
