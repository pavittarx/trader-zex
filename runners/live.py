"""Run a strategy LIVE with real capital (stage == live, exactly).

Hard gates, in order:
  1. stage must be exactly `live` (a sandbox strategy can NEVER run here)
  2. kill-switch halt state must be clear
  3. --i-am-sure must be passed explicitly (ENVIRONMENTS.md non-negotiable)
"""
from __future__ import annotations

import importlib
import sys

from core.manifest import Stage
from runners._common import load_manifest, require_not_halted, require_stage


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--i-am-sure"]
    confirmed = "--i-am-sure" in sys.argv
    if not args:
        sys.exit("usage: python -m runners.live <strategy> --i-am-sure [args...]")
    name, rest = args[0], args[1:]
    manifest = load_manifest(name)
    require_stage(manifest, Stage.live, exact=True)
    require_not_halted(manifest)
    if not confirmed:
        sys.exit(f"{name} is stage=live, but refusing without --i-am-sure. "
                 f"Real capital. Read strategies/{name}/STATUS.md first.")
    try:
        mod = importlib.import_module(f"strategies.{name}.live")
    except ModuleNotFoundError:
        sys.exit(f"strategies/{name}/live.py not found. The live TradingNode "
                 f"(real Fyers ExecutionClient) is not built yet — "
                 f"see the milestones in strategies/{name}/STATUS.md.")
    mod.main(rest)


if __name__ == "__main__":
    main()
