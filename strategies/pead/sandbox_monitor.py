"""PEAD sandbox forward monitor.

Runs daily sandbox cycles over a date range and emits gate metrics.
Use `--reset` to start from clean sandbox state.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from core.live import state as state_store
from core.research.stats import max_drawdown, sharpe
from strategies.pead.manifest import MANIFEST
from strategies.pead.paper import run_paper_cycle


def _business_days(frm: pd.Timestamp, to: pd.Timestamp) -> list[pd.Timestamp]:
    days: list[pd.Timestamp] = []
    d = frm
    while d <= to:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--date-from", required=True, help="YYYY-MM-DD")
    p.add_argument("--date-to", required=True, help="YYYY-MM-DD")
    p.add_argument("--lookback-days", type=int, default=800)
    p.add_argument("--reset", action="store_true", help="Reset sandbox paper state before replay")
    args = p.parse_args(argv)

    frm = pd.Timestamp(args.date_from)
    to = pd.Timestamp(args.date_to)
    state_name = MANIFEST.name
    positions_path = Path("~/.trader_zex/state/pead_sandbox_positions.json").expanduser()

    if args.reset:
        if positions_path.exists():
            positions_path.unlink()
        st = state_store.load(state_name)
        st.reset_halt()
        st.realized = []
        state_store.save(st)

    runs = 0
    for d in _business_days(frm, to):
        run_paper_cycle(
            as_of=d.date(),
            lookback_days=args.lookback_days,
            state_name=state_name,
            profile="sandbox",
        )
        runs += 1
        st = state_store.load(state_name)
        if st.halted:
            break

    st = state_store.load(state_name)
    rets = np.asarray(st.net_returns, dtype=float)
    out = {
        "date_from": frm.date().isoformat(),
        "date_to": to.date().isoformat(),
        "cycles_run": runs,
        "trades_closed": int(len(rets)),
        "halted": st.halted,
        "halt_reason": st.halted_reason,
        "win_rate": float((rets > 0).mean()) if len(rets) else 0.0,
        "mean_trade_ret": float(rets.mean()) if len(rets) else 0.0,
        "sharpe": float(sharpe(rets, periods=252)) if len(rets) > 1 else 0.0,
        "max_drawdown": float(max_drawdown(rets)) if len(rets) else 0.0,
        "gate_min_events_pass": len(rets) >= 15,
        "gate_no_kill_pass": not st.halted,
    }
    log_dir = Path("~/.trader_zex/logs/pead").expanduser()
    log_dir.mkdir(parents=True, exist_ok=True)
    out_path = log_dir / "sandbox_monitor_report.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
