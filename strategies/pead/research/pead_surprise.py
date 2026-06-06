"""Sharpen PEAD: (A) condition drift on reaction magnitude, (B) EPS surprise.

(A) Reaction-magnitude conditioning [reliable]: PEAD should be stronger for
    bigger news. Split events into LARGE vs SMALL |reaction| and compare the
    sign-based drift. If large-reaction events drift much more, trading only
    those fattens the per-trade margin (the thin-1-day-margin fix).

(B) EPS surprise [exploratory, data-limited]: nse_past_results gives only ~5
    quarters, so a clean YoY SUE isn't possible; QoQ EPS change is seasonally
    noisy. Reported with that caveat — IC(eps_qoq, drift).
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta

import numpy as np
import pandas as pd
from scipy import stats

from core import config  # noqa
from core.brokers.fyers.client import FyersClient
from strategies.pead.research.pead_event_ic import fetch_daily
import logging
logging.disable(logging.WARNING)


def results_with_eps(plain: str):
    import nsepython as n
    try:
        raw = n.nse_past_results(plain)
    except Exception:
        return []
    rows = (raw.get("resCmpData") or []) if isinstance(raw, dict) else []
    out = []
    for r in rows:
        dt = r.get("re_create_dt")
        if not dt:
            continue
        eps = r.get("re_basic_eps_for_cont_dic_opr") or r.get("re_basic_eps")
        try:
            eps = float(eps) if eps not in (None, "") else np.nan
        except Exception:
            eps = np.nan
        try:
            out.append((pd.to_datetime(dt, format="%d-%b-%Y"), eps))
        except Exception:
            pass
    out.sort(key=lambda x: x[0])
    return out


def sign_ls(sub, col):
    s = sub[["reaction", col]].dropna()
    sign = np.sign(s["reaction"]); v = (s[col] * sign)[sign != 0]
    if len(v) < 10:
        return None
    t = v.mean() / (v.std() / np.sqrt(len(v))) if v.std() > 0 else 0.0
    return v.mean() * 100, t, len(v)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", required=True)
    p.add_argument("--years", type=float, default=2.0)
    p.add_argument("--horizons", nargs="+", type=int, default=[1, 10, 20])
    args = p.parse_args()

    client = FyersClient()
    to = date.today(); frm = to - timedelta(days=int(args.years * 365) + 40)
    rows = []
    for s in args.symbols:
        plain = s.replace("NSE:", "").replace("-EQ", "")
        res = results_with_eps(plain)
        if not res:
            continue
        df = fetch_daily(client, s, frm, to)
        if df.empty or len(df) < 40:
            continue
        close = df.sort_index()["close"]; close.index = close.index.normalize()
        idx = close.index
        prev_eps = {}
        for k, (d, eps) in enumerate(res):
            if d < pd.Timestamp(frm):
                prev_eps[k] = eps; continue
            t = idx.searchsorted(d, side="right")
            if t < 1 or t + max(args.horizons) >= len(close):
                continue
            reaction = float(close.iloc[t] / close.iloc[t - 1] - 1)
            rec = {"reaction": reaction, "abs_react": abs(reaction)}
            # QoQ EPS surprise (prior quarter in the sorted list)
            pe = res[k - 1][1] if k >= 1 else np.nan
            rec["eps_qoq"] = (eps - pe) if (pd.notna(eps) and pd.notna(pe)) else np.nan
            for h in args.horizons:
                rec[f"drift_{h}"] = float(close.iloc[t + h] / close.iloc[t] - 1)
            rows.append(rec)

    df = pd.DataFrame(rows)
    print(f"events={len(df)}")
    if len(df) < 30:
        print("Too few events."); return

    # (A) reaction-magnitude split
    med = df["abs_react"].median()
    big, small = df[df["abs_react"] >= med], df[df["abs_react"] < med]
    print(f"\n(A) Reaction-magnitude split at |reaction|={med*100:.2f}%  "
          f"(LARGE n={len(big)}, SMALL n={len(small)}) — sign L/S drift, t:")
    print(f"{'horizon':>8}{'LARGE drift':>13}{'t':>7}{'SMALL drift':>13}{'t':>7}")
    for h in args.horizons:
        col = f"drift_{h}"; a, b = sign_ls(big, col), sign_ls(small, col)
        if a and b:
            print(f"{h:>8}{a[0]:>+12.2f}%{a[1]:>+7.2f}{b[0]:>+12.2f}%{b[1]:>+7.2f}")

    # (B) EPS surprise IC (caveated)
    eps_df = df.dropna(subset=["eps_qoq"])
    print(f"\n(B) EPS QoQ surprise [exploratory, n={len(eps_df)}] — IC(eps_qoq, drift):")
    if len(eps_df) >= 30:
        for h in args.horizons:
            sub = eps_df[["eps_qoq", f"drift_{h}"]].dropna()
            ic, _ = stats.spearmanr(sub["eps_qoq"], sub[f"drift_{h}"])
            ic_t = ic * np.sqrt(len(sub) - 2) / np.sqrt(1 - ic**2) if abs(ic) < 1 else 0.0
            print(f"   h={h:>2}  IC={ic:+.3f}  t={ic_t:+.2f}  n={len(sub)}")
    else:
        print("   too few with usable EPS — seasonality/data-depth limit.")


if __name__ == "__main__":
    main()
