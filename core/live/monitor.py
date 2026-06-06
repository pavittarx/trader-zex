"""Offline kill-switch monitor — evaluate a strategy's realized trades.

Usage:
    python -m core.live.monitor <strategy>                 # persisted state
    python -m core.live.monitor <strategy> --csv trades.csv  # external log
    python -m core.live.monitor <strategy> --reset-halt

The same KillSwitch the live RiskActor uses, run in batch — so what the
monitor reports IS what the live runner would do.
"""
from __future__ import annotations

import argparse

import pandas as pd

from core.live import state as state_store
from core.live.risk import build_killswitch


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("strategy")
    p.add_argument("--csv", help="realized-trades CSV with a net_ret column "
                                 "(default: persisted state)")
    p.add_argument("--reset-halt", action="store_true",
                   help="clear a tripped halt (record the decision in STATUS.md)")
    args = p.parse_args()

    from runners._common import load_manifest
    manifest = load_manifest(args.strategy)
    st = state_store.load(args.strategy)

    if args.reset_halt:
        if not st.halted:
            print(f"{args.strategy}: not halted, nothing to reset.")
            return
        print(f"{args.strategy}: clearing halt ({st.halted_reason} @ {st.halted_at})")
        st.reset_halt()
        state_store.save(st)
        return

    if args.csv:
        rets = pd.read_csv(args.csv)["net_ret"].tolist()
    else:
        rets = st.net_returns

    ks = build_killswitch(manifest)
    reason = ks.check(rets)
    print(f"{args.strategy}: trades={len(rets)} stage={manifest.stage.name} "
          f"halted={st.halted}")
    if reason:
        print(f"KILL: {reason}")
        if not args.csv:  # only persist when judging the canonical state
            st.halt(reason)
            state_store.save(st)
            print("Halt persisted — runners will refuse to start this strategy.")
    else:
        print("OK: no kill criterion tripped.")


if __name__ == "__main__":
    main()
