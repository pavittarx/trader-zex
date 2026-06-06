"""Liquidity-segmented PEAD: where does the edge survive realistic cost?

The capacity test showed PEAD concentrates in less-efficient (less-liquid)
names — but those cost more to trade. This segments events by their stock's
liquidity (median daily traded value) into terciles, measures the drift per
bucket, and applies BUCKET-APPROPRIATE round-trip cost:

  high liquidity (blue-chip)  -> cheap   (tight spread)
  mid  liquidity              -> medium
  low  liquidity (small-cap)  -> expensive (wide spread, slippage)

The tradable question: is there a bucket where the NET drift is positive and
significant? Uses the validated nse-exact-date + t+1 reaction method.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta

import numpy as np
import pandas as pd

from core import config  # noqa
from core.fyers_client import FyersClient
from scripts.pead_event_ic import fetch_daily, result_dates
import logging
logging.disable(logging.WARNING)


def collect(client, symbols, frm, to, horizons, thresh):
    rows = []
    for s in symbols:
        plain = s.replace("NSE:", "").replace("-EQ", "")
        dates = result_dates(plain)
        if not dates:
            continue
        df = fetch_daily(client, s, frm, to)
        if df.empty or len(df) < 60:
            continue
        df = df.sort_index(); df.index = df.index.normalize()
        close, vol = df["close"], df["volume"]
        liq = float((close * vol).median())          # median daily traded value (Rs)
        idx = close.index
        for d in dates:
            if d < pd.Timestamp(frm):
                continue
            t = idx.searchsorted(d, side="right")
            if t < 1 or t + max(horizons) >= len(close):
                continue
            reaction = float(close.iloc[t] / close.iloc[t - 1] - 1)
            if abs(reaction) < thresh:
                continue
            rec = {"sym": s, "liq": liq, "reaction": reaction}
            for h in horizons:
                rec[f"drift_{h}"] = float(close.iloc[t + h] / close.iloc[t] - 1)
            rows.append(rec)
    return pd.DataFrame(rows)


def ls_stats(sub, col, cost):
    sign = np.sign(sub["reaction"])
    v = (sub[col] * sign)[sign != 0].dropna()
    if len(v) < 10:
        return None
    gross = v.mean()
    t = gross / (v.std() / np.sqrt(len(v))) if v.std() > 0 else 0.0
    return gross * 100, (gross - cost) * 100, t, len(v)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", required=True)
    p.add_argument("--years", type=float, default=2.0)
    p.add_argument("--thresh", type=float, default=0.02)
    p.add_argument("--horizons", nargs="+", type=int, default=[1, 20])
    # bucket round-trip costs (bps): low-liq is most expensive
    p.add_argument("--costs-bps", nargs=3, type=float, default=[15, 30, 55],
                   metavar=("HIGH", "MID", "LOW"))
    args = p.parse_args()

    client = FyersClient()
    to = date.today(); frm = to - timedelta(days=int(args.years * 365) + 40)
    df = collect(client, args.symbols, frm, to, args.horizons, args.thresh)
    print(f"events={len(df)}  (|reaction|>={args.thresh*100:.0f}%)")
    if len(df) < 30:
        print("Too few events."); return

    # tercile by liquidity
    df["bucket"] = pd.qcut(df["liq"], 3, labels=["LOW", "MID", "HIGH"])
    cost_map = {"HIGH": args.costs_bps[0] / 1e4, "MID": args.costs_bps[1] / 1e4,
                "LOW": args.costs_bps[2] / 1e4}
    print(f"\nbucket costs: HIGH={args.costs_bps[0]} MID={args.costs_bps[1]} "
          f"LOW={args.costs_bps[2]} bps round-trip")
    print(f"\n{'bucket':>6}{'med_liq(Rs cr/day)':>20}{'n':>5}  | per horizon: gross% / NET% (t)")
    for b in ["HIGH", "MID", "LOW"]:
        sub = df[df["bucket"] == b]
        medliq = sub["liq"].median() / 1e7   # Rs crore
        line = f"{b:>6}{medliq:>20.1f}{len(sub):>5}  |"
        for h in args.horizons:
            r = ls_stats(sub, f"drift_{h}", cost_map[b])
            if r:
                line += f"  h{h}: {r[0]:+.2f}/{r[1]:+.2f}% (t{r[2]:+.1f})"
        print(line)
    print("\nTradable = a bucket with positive, significant NET drift. If only the LOW")
    print("bucket has gross edge but its higher cost erases it, PEAD is not tradable.")


if __name__ == "__main__":
    main()
