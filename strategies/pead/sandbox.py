"""PEAD sandbox entrypoint.

Current implementation runs a one-shot forward paper cycle using live/cached
daily bars and records trades under the manifest state key (`pead`) so
kill-switch checks are enforced by standard sandbox/live monitors.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime

from core.live.fyers_sandbox import get_shared_session
from strategies.pead.manifest import MANIFEST
from strategies.pead.paper import run_paper_cycle


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="strategies.pead.sandbox")
    p.add_argument("--as-of", type=str, default=None, help="YYYY-MM-DD (default: today)")
    p.add_argument("--lookback-days", type=int, default=800)
    args = p.parse_args(argv)

    as_of = datetime.strptime(args.as_of, "%Y-%m-%d").date() if args.as_of else date.today()
    session = get_shared_session(require_headless=True)
    out = run_paper_cycle(
        as_of=as_of,
        lookback_days=args.lookback_days,
        state_name=MANIFEST.name,
        profile="sandbox",
        market_client=session.market,
        execution_client=session.execution,
    )
    import json
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
