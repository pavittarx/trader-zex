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

import config  # noqa
from fyers_client import FyersClient
import logging
logging.disable(logging.WARNING)


def fetch_daily(client, sym, frm, to, chunk_days=360):
    """Daily history in <=chunk_days windows (Fyers caps 1D at 366 days/request)."""
    parts, cur = [], frm
    while cur <= to:
        end = min(cur + timedelta(days=chunk_days - 1), to)
        try:
            df = client.get_history(sym, "D", date_from=cur, date_to=end)
            if not df.empty:
                parts.append(df)
        except Exception:
            pass
        cur = end + timedelta(days=1)
    if not parts:
        return pd.DataFrame()
    allp = pd.concat(parts).sort_index()
    return allp[~allp.index.duplicated()]


def result_dates(sym_plain: str) -> list[pd.Timestamp]:
    import nsepython as n
    try:
        raw = n.nse_past_results(sym_plain)
    except Exception:
        return []
    rows = raw.get("resCmpData", []) if isinstance(raw, dict) else []
    out = []
    for r in rows:
        dt = r.get("re_create_dt")
        if dt:
            try:
                out.append(pd.to_datetime(dt, format="%d-%b-%Y"))
            except Exception:
                pass
    return sorted(set(out))


def events_for(close: pd.Series, dates: list[pd.Timestamp], horizons: list[int]):
    """Return list of dicts: reaction + drift over each horizon, no look-ahead."""
    idx = close.index
    out = []
    for d in dates:
        # Results are announced after-hours on re_create_dt; the market reacts
        # the NEXT session. So the reaction day is the first trading day STRICTLY
        # after the announcement (verified via scripts/_align_check.py).
        t = idx.searchsorted(d, side="right")
        if t < 1 or t >= len(idx):
            continue
        reaction = close.iloc[t] / close.iloc[t - 1] - 1   # move into the reaction day
        rec = {"reaction": float(reaction)}
        ok = True
        for h in horizons:
            if t + h >= len(close):
                ok = False; break
            rec[f"drift_{h}"] = float(close.iloc[t + h] / close.iloc[t] - 1)
        if ok:
            out.append(rec)
    return out


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
    print("\nPositive IC = drift continues (underreaction/PEAD). The sign L/S is the")
    print("tradable form: hold N days; net of ~15-25 bps cost spread over the move.")


if __name__ == "__main__":
    main()
