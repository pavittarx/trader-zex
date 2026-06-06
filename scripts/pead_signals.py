"""Daily PEAD signal generator + kill-switch monitor (paper/live deployment).

`signals` mode: as of a date, scan the universe for earnings reactions and print
the actions implied by the locked spec (PEAD_PLAYBOOK.md):
  ENTER TODAY  — reaction landed today (|reaction|>=2%): open at the close.
  HOLDING      — in the 20-day window: keep.
  EXIT TODAY   — 20 sessions since reaction: close.

`monitor` mode: read a CSV of realized trades (date,symbol,net_ret) and evaluate
the pre-registered kill-criteria (trailing-20 mean, win rate, drawdown).

Use --as-of to run for any historical date (the data here is stale, so 'today'
shows nothing; --as-of 2024-07-15 demonstrates the tool).
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta

import numpy as np
import pandas as pd

from core import config  # noqa
from core.brokers.fyers.client import FyersClient
from scripts.pead_event_ic import fetch_daily, result_dates
from core.pead_core import kill_check
import logging
logging.disable(logging.WARNING)

HOLD, THRESH = config.PEAD_HOLD_BARS, config.PEAD_THRESH


def signals(client, symbols, as_of: date):
    frm = as_of - timedelta(days=120)
    actions = {"ENTER TODAY": [], "EXIT TODAY": [], "HOLDING": []}
    for s in symbols:
        plain = s.replace("NSE:", "").replace("-EQ", "")
        dates = result_dates(plain)
        if not dates:
            continue
        df = fetch_daily(client, s, frm, as_of)
        if df.empty or len(df) < 25:
            continue
        close = df.sort_index()["close"]; close.index = close.index.normalize()
        idx = close.index
        as_of_pos = idx.searchsorted(pd.Timestamp(as_of), side="right") - 1  # last session <= as_of
        if as_of_pos < 1:
            continue
        for d in dates:
            t = idx.searchsorted(d, side="right")           # reaction day
            if t < 1 or t > as_of_pos:
                continue
            reaction = close.iloc[t] / close.iloc[t - 1] - 1
            if abs(reaction) < THRESH:
                continue
            age = as_of_pos - t                              # sessions since reaction
            side = "LONG" if reaction > 0 else "SHORT"
            row = f"{s:<18} {side:<5} react={reaction:+.1%}  reaction_day={idx[t].date()}  age={age}d"
            if age == 0:
                actions["ENTER TODAY"].append(row)
            elif age == HOLD:
                actions["EXIT TODAY"].append(row)
            elif 0 < age < HOLD:
                actions["HOLDING"].append(row + f"  exit~{idx[min(t+HOLD,len(idx)-1)].date()}")
    return actions


def monitor(path: str):
    df = pd.read_csv(path)
    r = df["net_ret"].astype(float).values
    eq = np.cumprod(1 + r); dd = (eq / np.maximum.accumulate(eq) - 1).min()
    tr = r[-config.PEAD_KILL_TRAILING:]
    print(f"trades={len(r)}  cum_return={ (eq[-1]-1)*100:+.1f}%  maxDD={dd*100:+.1f}%")
    print(f"trailing-{config.PEAD_KILL_TRAILING}: mean={tr.mean()*100:+.2f}%  win%={ (tr>0).mean()*100:.0f}")
    reason = kill_check(r)   # canonical kill-criteria (pead_core)
    print("KILL-SWITCH:", f"{reason} → HALT" if reason else "OK — no criterion tripped")


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="mode", required=True)
    a = sub.add_parser("signals"); a.add_argument("--symbols", nargs="+", required=True)
    a.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    b = sub.add_parser("monitor"); b.add_argument("--trades-csv", required=True)
    args = p.parse_args()

    if args.mode == "monitor":
        monitor(args.trades_csv); return

    acts = signals(FyersClient(), args.symbols, args.as_of)
    print(f"=== PEAD signals as of {args.as_of} ===")
    for k in ("EXIT TODAY", "ENTER TODAY", "HOLDING"):
        print(f"\n{k} ({len(acts[k])}):")
        for row in acts[k]:
            print("  " + row)
    if not any(acts.values()):
        print("\n(no active positions — try --as-of on a date within ~20 sessions of an earnings reaction)")


if __name__ == "__main__":
    main()
