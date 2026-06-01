"""Screen candidate daily features for predictive power (IC vs next-day return).

Cheap: one daily fetch per symbol covers all dates. Point-in-time — every
feature at day D uses only data up to D's close; target is D->D+1 return.
Cross-sectional Spearman per day, averaged -> IC, t-stat per feature.
"""
import argparse
import logging
from datetime import date

import numpy as np
import pandas as pd
from scipy import stats

import config  # noqa
from fyers_client import FyersClient

logging.disable(logging.WARNING)


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).rolling(n).mean()
    dn = (-d.clip(upper=0)).rolling(n).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def features(df: pd.DataFrame) -> pd.DataFrame:
    c, h, l, v = df["close"], df["high"], df["low"], df["volume"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    out = pd.DataFrame(index=df.index)
    out["ret_1d"] = c.pct_change(1)
    out["ret_5d"] = c.pct_change(5)
    out["ret_10d"] = c.pct_change(10)
    out["rsi_14"] = rsi(c)
    out["vol_z"] = (v - v.rolling(20).mean()) / v.rolling(20).std()
    out["range_ratio"] = (h - l) / c
    out["dist_20d_hi"] = (c - c.rolling(20).max()) / c.rolling(20).max()
    out["gap"] = df["open"] / c.shift() - 1
    out["mom_per_atr"] = c.pct_change(5) / (atr / c)
    out["fwd_1d"] = c.shift(-1) / c - 1   # TARGET (next-day return)
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", required=True)
    p.add_argument("--date-from", type=date.fromisoformat, required=True)
    p.add_argument("--date-to", type=date.fromisoformat, default=date.today())
    args = p.parse_args()

    client = FyersClient()
    frames = {}
    for s in args.symbols:
        try:
            df = client.get_history(s, "D", date_from=args.date_from, date_to=args.date_to)
            if not df.empty and len(df) > 25:
                frames[s] = features(df.sort_index())
        except Exception:
            pass

    if len(frames) < 5:
        print(f"Only {len(frames)} symbols — need >=5 for cross-sectional IC.")
        return

    feat_cols = [c for c in next(iter(frames.values())).columns if c != "fwd_1d"]
    # Build a long panel: (date, symbol) -> features + fwd
    panel = pd.concat({s: f for s, f in frames.items()}, names=["symbol", "date"]).reset_index()

    print(f"symbols={len(frames)}  obs={len(panel.dropna())}")
    print(f"{'feature':<14}{'mean_IC':>9}{'t_stat':>8}{'IC>0%':>7}{'days':>6}")
    rows = []
    for col in feat_cols:
        ics = []
        for d, g in panel.groupby("date"):
            sub = g[[col, "fwd_1d"]].dropna()
            if len(sub) >= 5:
                ic, _ = stats.spearmanr(sub[col], sub["fwd_1d"])
                if not np.isnan(ic):
                    ics.append(ic)
        if len(ics) < 5:
            continue
        ics = np.array(ics)
        t = ics.mean() / (ics.std() / np.sqrt(len(ics))) if ics.std() > 0 else 0.0
        rows.append((col, ics.mean(), t, (ics > 0).mean() * 100, len(ics)))
    for col, m, t, pos, n in sorted(rows, key=lambda r: -abs(r[1])):
        flag = "  <-- signal" if abs(t) >= 2 and abs(m) >= 0.03 else ""
        print(f"{col:<14}{m:>+9.4f}{t:>+8.2f}{pos:>6.0f}%{n:>6}{flag}")


if __name__ == "__main__":
    main()
