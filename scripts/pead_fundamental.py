"""Fundamental-surprise PEAD: does YoY earnings surprise predict drift?

Uses screener.in deep EPS (scripts/screener_data) for a real seasonal surprise
(EPS[Q] - EPS[Q-4]), which nse's 5 quarters couldn't support. Dates each event
by snapping to the max-volume day in the post-quarter-end reporting window
(screener has no clean announcement date). Compares the fundamental surprise to
the price-reaction proxy, and tests whether the two together sharpen the signal.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta

import numpy as np
import pandas as pd
from scipy import stats

from core import config  # noqa
from core.fyers_client import FyersClient
from scripts.pead_event_ic import fetch_daily
from scripts.screener_data import get_quarterly_eps
import logging
logging.disable(logging.WARNING)


def events_for(df: pd.DataFrame, eps: pd.Series, horizons, lag_lo=18, lag_hi=72):
    """df: daily OHLCV (index normalized). eps: quarter-end -> EPS. Yield event dicts."""
    df = df.sort_index(); df.index = df.index.normalize()
    close, vol = df["close"], df["volume"]
    idx = close.index
    eps = eps.sort_index()
    out = []
    for k in range(4, len(eps)):                       # need Q-4 for YoY surprise
        qe = eps.index[k]
        sue = eps.iloc[k] - eps.iloc[k - 4]            # YoY earnings surprise (seasonal RW)
        if pd.isna(sue):
            continue
        # reporting window after quarter-end; reaction = max-volume day in it
        lo, hi = qe + timedelta(days=lag_lo), qe + timedelta(days=lag_hi)
        win = vol[(idx >= lo) & (idx <= hi)]
        if win.empty:
            continue
        rd = win.idxmax()                              # results-day volume spike
        t = idx.get_loc(rd)
        if t < 1 or t + max(horizons) >= len(close):
            continue
        rec = {"sue": float(sue),
               "reaction": float(close.iloc[t] / close.iloc[t - 1] - 1)}
        for h in horizons:
            rec[f"drift_{h}"] = float(close.iloc[t + h] / close.iloc[t] - 1)
        out.append(rec)
    return out


def ic(sub, x, y):
    s = sub[[x, y]].dropna()
    if len(s) < 20:
        return None
    r, _ = stats.spearmanr(s[x], s[y])
    t = r * np.sqrt(len(s) - 2) / np.sqrt(1 - r**2) if abs(r) < 1 else 0.0
    return r, t, len(s)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", required=True)
    p.add_argument("--years", type=float, default=2.5)
    p.add_argument("--horizons", nargs="+", type=int, default=[1, 5, 20])
    args = p.parse_args()

    client = FyersClient()
    to = date.today(); frm = to - timedelta(days=int(args.years * 365) + 80)
    rows = []
    nsym = 0
    for s in args.symbols:
        plain = s.replace("NSE:", "").replace("-EQ", "")
        eps = get_quarterly_eps(plain)
        if eps.empty or len(eps) < 6:
            continue
        df = fetch_daily(client, s, frm, to)
        if df.empty or len(df) < 60:
            continue
        nsym += 1
        rows += events_for(df, eps, args.horizons)

    df = pd.DataFrame(rows)
    print(f"symbols={nsym}  events={len(df)}")
    if len(df) < 30:
        print("Too few events."); return

    print(f"\n{'horizon':>8}{'IC(SUE)':>10}{'t':>7}{'IC(react)':>11}{'t':>7}  | SUE-sorted L/S, t")
    for h in args.horizons:
        col = f"drift_{h}"
        a = ic(df, "sue", col)
        b = ic(df, "reaction", col)
        # sign-based L/S on SUE: long positive surprise, short negative
        s = df[["sue", col]].dropna(); sign = np.sign(s["sue"])
        ls = (s[col] * sign)[sign != 0]
        t = ls.mean() / (ls.std() / np.sqrt(len(ls))) if ls.std() > 0 else 0.0
        if a and b:
            print(f"{h:>8}{a[0]:>+10.3f}{a[1]:>+7.2f}{b[0]:>+11.3f}{b[1]:>+7.2f}  | "
                  f"{ls.mean()*100:+.2f}%  t={t:+.2f}  n={len(ls)}")
    print("\nIC(SUE)=fundamental surprise; IC(react)=price-reaction proxy. If SUE adds")
    print("signal beyond the reaction, the fundamental data was worth scraping.")


if __name__ == "__main__":
    main()
