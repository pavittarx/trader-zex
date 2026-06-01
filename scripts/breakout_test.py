"""Volatility-compression breakout — a LOW-TURNOVER intraday test.

Setup (per symbol):
  - Qualify day D only if the PRIOR day D-1 was an NR7 (narrowest range of the
    last 7 days) — a quiet, compressed day. This is selective: ~1 day in 7.
  - On day D, place stop orders at D-1's high (long) and low (short).
    First level breached triggers; enter there (or at the open if D gaps
    through the level — realistic, no optimistic fill). Exit at D's close.
  - One trade per qualifying day. Few trades => cost is a small fraction of the
    move, unlike daily-rebalance L/S.

No look-ahead: D-1 high/low and the NR7 flag are known before D opens; entry is
at a level/price reachable in real time; exit at the close.
"""
from __future__ import annotations

import argparse
import time
from datetime import date, timedelta

import numpy as np
import pandas as pd

import config  # noqa
from fyers_client import FyersClient
import logging
logging.disable(logging.WARNING)


def fetch_intraday(client, sym, frm, to, resolution="15", chunk_days=95):
    parts, cur = [], frm
    while cur <= to:
        end = min(cur + timedelta(days=chunk_days - 1), to)
        try:
            df = client.get_history(sym, resolution, date_from=cur, date_to=end)
            if not df.empty:
                parts.append(df)
        except Exception:
            pass
        cur = end + timedelta(days=1)
        time.sleep(config.API_SLEEP_SECONDS)
    if not parts:
        return pd.DataFrame()
    allp = pd.concat(parts).sort_index()
    return allp[~allp.index.duplicated()]


def trades_for_symbol(intr: pd.DataFrame, nr: int, rt: float) -> list[float]:
    intr = intr.copy()
    intr["d"] = intr.index.normalize()
    days = sorted(intr["d"].unique())
    # daily ranges for NR detection
    daily = intr.groupby("d").agg(high=("high", "max"), low=("low", "min"),
                                  close=("close", "last"))
    daily["range"] = daily["high"] - daily["low"]
    out = []
    for i in range(nr, len(days)):
        d = days[i]
        prev = days[i - 1]
        # NR7: prior day's range is the smallest of the prior `nr` days
        window = daily["range"].iloc[i - nr:i]          # days [i-nr, i-1]
        if daily["range"].loc[prev] > window.min() + 1e-12:
            continue                                     # prior day not the narrowest
        ph, pl = daily["high"].loc[prev], daily["low"].loc[prev]
        bars = intr[intr["d"] == d].sort_index()
        if len(bars) < 3:
            continue
        day_open = bars["open"].iloc[0]
        day_close = bars["close"].iloc[-1]
        entry = side = None
        # gap-through at open?
        if day_open > ph:
            entry, side = day_open, "long"
        elif day_open < pl:
            entry, side = day_open, "short"
        else:
            for _, b in bars.iterrows():
                if b["high"] >= ph:
                    entry, side = ph, "long"; break
                if b["low"] <= pl:
                    entry, side = pl, "short"; break
        if entry is None:
            continue                                     # never broke out
        r = (day_close / entry - 1) if side == "long" else (entry / day_close - 1)
        out.append(r - rt)                               # net of round-trip cost
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", required=True)
    p.add_argument("--date-from", type=date.fromisoformat, required=True)
    p.add_argument("--date-to", type=date.fromisoformat, default=date.today())
    p.add_argument("--resolution", default="15")
    p.add_argument("--nr", type=int, default=7, help="NR-n compression lookback")
    p.add_argument("--rt-bps", type=float, default=15.0)
    args = p.parse_args()

    client = FyersClient()
    all_trades, n_sym, total_days = [], 0, 0
    rt = args.rt_bps / 1e4
    for s in args.symbols:
        intr = fetch_intraday(client, s, args.date_from, args.date_to, args.resolution)
        if intr.empty or intr.index.normalize().nunique() < args.nr + 5:
            continue
        n_sym += 1
        total_days += intr.index.normalize().nunique()
        all_trades += trades_for_symbol(intr, args.nr, rt)

    n = len(all_trades)
    print(f"symbols={n_sym}  NR{args.nr}  rt={args.rt_bps}bps")
    if n < 20:
        print(f"Only {n} trades — too few."); return
    a = np.array(all_trades)
    per_trade_bps = a.mean() * 1e4
    t = a.mean() / (a.std() / np.sqrt(n)) if a.std() > 0 else 0.0
    trades_per_symbol_year = n / n_sym / (total_days / n_sym / 252)
    ann = per_trade_bps / 1e4 * trades_per_symbol_year * 100   # rough, per symbol
    print(f"trades={n}  (~{trades_per_symbol_year:.0f}/symbol/yr)")
    print(f"net per trade = {per_trade_bps:+.1f} bps   t={t:+.2f}   win%={(a>0).mean()*100:.0f}")
    print(f"rough ann/symbol = {ann:+.1f}%   (per-trade edge x trade frequency)")
    print("\nTradable only if net-per-trade is solidly positive with t>2 —")
    print("low turnover means cost is paid rarely, but the move must clear it.")


if __name__ == "__main__":
    main()
