"""PEAD event study: does the earnings-day price reaction predict later drift?

Edge hypothesis: investors underreact to earnings; the results-day move
continues (drifts) over the following days. Low turnover (~4 events/yr/stock).

For each symbol:
  - results dates from nsepython.nse_past_results (re_create_dt)
  - reaction  = return on the first trading day on/after the announcement
                (results often hit after-hours, so the reaction is next session)
  - drift_N   = return from the reaction day's close to N trading days later

Pooled Spearman IC(reaction, drift_N) > 0 => underreaction/drift (PEAD).
Also reports a sign-based long/short: long positive-reaction events, short
negative, hold N days — mean drift and t-stat, the tradable form.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta

import numpy as np
import pandas as pd
from scipy import stats

from core import config  # noqa
from core.brokers.fyers.client import FyersClient
from core.research.data import fetch_daily            # noqa: F401 (re-export)
from core.research.events_nse import result_dates     # noqa: F401 (re-export)
from core.research.event_study import events_with_drift as events_for
import logging
logging.disable(logging.WARNING)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", required=True)
    p.add_argument("--years", type=float, default=2.0)
    p.add_argument("--horizons", nargs="+", type=int, default=[1, 5, 10, 20])
    args = p.parse_args()

    client = FyersClient()
    to = date.today()
    frm = to - timedelta(days=int(args.years * 365) + 40)
    rows = []
    nsym = 0
    for s in args.symbols:
        plain = s.replace("NSE:", "").replace("-EQ", "")
        dates = result_dates(plain)
        if not dates:
            continue
        df = fetch_daily(client, s, frm, to)
        if df.empty or len(df) < 40:
            continue
        close = df.sort_index()["close"]
        close.index = close.index.normalize()
        ev = events_for(close, [d for d in dates if d >= pd.Timestamp(frm)], args.horizons)
        for e in ev:
            e["symbol"] = s
        rows += ev
        nsym += 1

    df = pd.DataFrame(rows)
    print(f"symbols={nsym}  events={len(df)}")
    if len(df) < 20:
        print("Too few events."); return

    print(f"\n{'horizon':>8}{'IC(react,drift)':>17}{'t':>7}   | sign L/S mean drift, t")
    for h in args.horizons:
        col = f"drift_{h}"
        sub = df[["reaction", col]].dropna()
        if len(sub) < 20:
            continue
        ic, _ = stats.spearmanr(sub["reaction"], sub[col])
        ic_t = ic * np.sqrt(len(sub) - 2) / np.sqrt(1 - ic**2) if abs(ic) < 1 else 0.0
        # sign-based long/short: long if reaction>0 else short; pnl = drift*sign
        sign = np.sign(sub["reaction"])
        ls = (sub[col] * sign)
        ls = ls[sign != 0]
        t = ls.mean() / (ls.std() / np.sqrt(len(ls))) if ls.std() > 0 else 0.0
        print(f"{h:>8}{ic:>+17.4f}{ic_t:>+7.2f}   | {ls.mean()*100:+6.2f}%  t={t:+.2f}  n={len(ls)}")
    # --- Sub-period robustness: does the drift hold in BOTH halves? ---
    if "date" in df.columns:
        med = df["date"].sort_values().iloc[len(df) // 2]
        h1 = df[df["date"] <= med]
        h2 = df[df["date"] > med]
        print(f"\nSub-period split at {pd.Timestamp(med).date()}  "
              f"(H1 n={len(h1)}, H2 n={len(h2)}) — sign L/S mean drift, t:")
        print(f"{'horizon':>8}{'H1 drift':>12}{'H1 t':>7}{'H2 drift':>12}{'H2 t':>7}")
        for h in args.horizons:
            col = f"drift_{h}"
            def ls(sub):
                s = sub[["reaction", col]].dropna()
                sign = np.sign(s["reaction"]); v = (s[col] * sign)[sign != 0]
                if len(v) < 10:
                    return None
                t = v.mean() / (v.std() / np.sqrt(len(v))) if v.std() > 0 else 0.0
                return v.mean() * 100, t
            a, b = ls(h1), ls(h2)
            if a and b:
                print(f"{h:>8}{a[0]:>+11.2f}%{a[1]:>+7.2f}{b[0]:>+11.2f}%{b[1]:>+7.2f}")
        print("\nHolds in BOTH halves = robust. Works in only one = period-specific (fragile).")

    print("\nPositive IC = drift continues (underreaction/PEAD). The sign L/S is the")
    print("tradable form: hold N days; net of ~15-25 bps cost spread over the move.")


if __name__ == "__main__":
    main()
