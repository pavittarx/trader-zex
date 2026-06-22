"""Momentum sandbox entrypoint.

Uses shared Fyers sandbox session so multiple strategies can reuse one
market/execution client set in a single process.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime

from core.live.fyers_sandbox import get_shared_session
from strategies.momentum.manifest import MANIFEST
from strategies.momentum.paper import run_paper_cycle


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="strategies.momentum.sandbox")
    p.add_argument("--as-of", type=str, default=None, help="YYYY-MM-DD (default: today)")
    p.add_argument("--n-symbols", type=int, default=50)
    p.add_argument("--lookback-days", type=int, default=900)
    args = p.parse_args(argv)

    as_of = datetime.strptime(args.as_of, "%Y-%m-%d").date() if args.as_of else date.today()
    session = get_shared_session(require_headless=True)
    out = run_paper_cycle(
        as_of=as_of,
        n_symbols=args.n_symbols,
        lookback_days=args.lookback_days,
        state_name=MANIFEST.name,
        profile="sandbox",
        market_client=session.market,
        execution_client=session.execution,
    )
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
