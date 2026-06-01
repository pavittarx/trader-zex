"""Does limit-order entry rescue intraday continuation from the cost wall?

Continuation: gap-up -> go long, gap-down -> go short, exit at close.
We compare two entries on the SAME signal set (names with |gap| >= gap_min):

  MARKET  : enter at the 9:30 price, pay the full round-trip cost. Fills always.
  LIMIT@d : post a passive limit `d` bps better than 9:30. Filled ONLY if a later
            bar trades through it (else missed -> no trade). Saves spread on the
            entry leg, but suffers adverse selection — trades that run straight
            in our favour never pull back to the limit and are missed.

Honest accounting: a missed signal is simply not traded (0, not a loss). The
question is whether net-per-FILLED-trade under limits beats the market baseline
once you account for which trades actually fill.
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


def collect(intr: pd.DataFrame, gap_min: float):
    """Yield per-trade dicts: direction, ref price, intraday low/high path, close."""
    intr = intr.copy()
    intr["d"] = intr.index.normalize()
    days = sorted(intr["d"].unique())
    daily_close = intr.groupby("d")["close"].last()
    trades = []
    for i in range(1, len(days)):
        d, prev = days[i], days[i - 1]
        bars = intr[intr["d"] == d].sort_index()
        if len(bars) < 3:
            continue
        prev_close = daily_close.loc[prev]
        day_open = bars["open"].iloc[0]
        gap = day_open / prev_close - 1
        if abs(gap) < gap_min:
            continue
        ref = bars["close"].iloc[0]            # 9:30 price (close of first bar)
        rest = bars.iloc[1:]                   # bars after the ref bar
        if rest.empty:
            continue
        trades.append({
            "dir": 1 if gap > 0 else -1,       # continuation
            "ref": ref,
            "low": rest["low"].min(),
            "high": rest["high"].max(),
            "close": bars["close"].iloc[-1],
        })
    return trades


def eval_market(trades, rt):
    r = []
    for t in trades:
        ret = (t["close"] / t["ref"] - 1) * t["dir"]
        r.append(ret - rt)
    return np.array(r)


def eval_limit(trades, offset, rt):
    """Passive limit `offset` better than ref; filled only if path trades through."""
    r = []
    for t in trades:
        if t["dir"] == 1:                      # long: buy-limit below ref
            L = t["ref"] * (1 - offset)
            filled = t["low"] <= L
        else:                                  # short: sell-limit above ref
            L = t["ref"] * (1 + offset)
            filled = t["high"] >= L
        if not filled:
            continue
        ret = (t["close"] / L - 1) * t["dir"]
        r.append(ret - rt)
    return np.array(r), len(r) / max(len(trades), 1)


def summary(a):
    if len(a) < 20:
        return None
    t = a.mean() / (a.std() / np.sqrt(len(a))) if a.std() > 0 else 0.0
    return a.mean() * 1e4, t, (a > 0).mean() * 100, len(a)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", required=True)
    p.add_argument("--date-from", type=date.fromisoformat, required=True)
    p.add_argument("--date-to", type=date.fromisoformat, default=date.today())
    p.add_argument("--resolution", default="15")
    p.add_argument("--gap-min", type=float, default=0.01)
    p.add_argument("--rt-market", type=float, default=15.0, help="market round-trip bps")
    p.add_argument("--rt-limit", type=float, default=10.0, help="limit-entry round-trip bps")
    args = p.parse_args()

    client = FyersClient()
    trades = []
    nsym = 0
    for s in args.symbols:
        intr = fetch_intraday(client, s, args.date_from, args.date_to, args.resolution)
        if intr.empty or intr.index.normalize().nunique() < 10:
            continue
        nsym += 1
        trades += collect(intr, args.gap_min)

    print(f"symbols={nsym}  gap_min={args.gap_min*100:.1f}%  signals={len(trades)}  "
          f"rt_market={args.rt_market}bps  rt_limit={args.rt_limit}bps")
    if len(trades) < 20:
        print("Too few signals."); return

    print(f"\n{'entry':>14}{'fill%':>7}{'net_bps/trade':>15}{'t':>7}{'win%':>6}{'n':>6}")
    m = summary(eval_market(trades, args.rt_market / 1e4))
    if m:
        print(f"{'MARKET@9:30':>14}{100:>6.0f}%{m[0]:>15.1f}{m[1]:>+7.2f}{m[2]:>5.0f}%{m[3]:>6}")
    for off in (0, 5, 10, 20):
        a, fr = eval_limit(trades, off / 1e4, args.rt_limit / 1e4)
        s = summary(a)
        if s:
            print(f"{'LIMIT -'+str(off)+'bps':>14}{fr*100:>6.0f}%{s[0]:>15.1f}{s[1]:>+7.2f}{s[2]:>5.0f}%{s[3]:>6}")
    print("\nLimit wins only if net_bps/trade beats MARKET with a usable fill%.")
    print("Low fill% on a continuation bet = adverse selection (missed the runners).")


if __name__ == "__main__":
    main()
