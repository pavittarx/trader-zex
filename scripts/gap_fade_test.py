"""Cost-aware gap-fade long/short, intraday (MIS-compatible).

Each day at the open: rank the universe by overnight gap (open/prev_close-1).
LONG the biggest gap-DOWNs, SHORT the biggest gap-UPs, hold open->close, flat
at close. One round trip per name per day. Reports gross AND net of cost.

A 'threshold' variant only trades names whose |gap| exceeds a cut, to test
whether the effect concentrates in large gaps (and cuts turnover/cost).
"""
import argparse
from datetime import date

import numpy as np
import pandas as pd

import config  # noqa
from fyers_client import FyersClient
import logging
logging.disable(logging.WARNING)


def stats_line(daily: np.ndarray, rt_cost: float, label: str) -> None:
    if len(daily) < 20:
        print(f"  {label:<22} (too few days: {len(daily)})"); return
    net = daily - rt_cost                      # one round trip per day
    ann_g = ((1 + daily.mean()) ** 252 - 1) * 100
    ann_n = ((1 + net.mean()) ** 252 - 1) * 100
    t = daily.mean() / (daily.std() / np.sqrt(len(daily))) if daily.std() > 0 else 0.0
    sharpe_n = (net.mean() / net.std()) * np.sqrt(252) if net.std() > 0 else 0.0
    print(f"  {label:<22} gross={ann_g:+7.1f}%  net={ann_n:+7.1f}%  "
          f"t={t:+5.2f}  net_Sharpe={sharpe_n:+5.2f}  days={len(daily)}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", required=True)
    p.add_argument("--date-from", type=date.fromisoformat, required=True)
    p.add_argument("--date-to", type=date.fromisoformat, default=date.today())
    p.add_argument("--k", type=int, default=5)
    p.add_argument("--rt-bps", type=float, default=20.0, help="round-trip cost, bps")
    args = p.parse_args()

    client = FyersClient()
    gap, intr = {}, {}
    for s in args.symbols:
        try:
            df = client.get_history(s, "D", date_from=args.date_from, date_to=args.date_to)
            if df.empty or len(df) < 30:
                continue
            df = df.sort_index()
            gap[s] = df["open"] / df["close"].shift() - 1
            intr[s] = df["close"] / df["open"] - 1
        except Exception:
            pass
    if len(gap) < 10:
        print(f"Only {len(gap)} symbols."); return
    G, I = pd.DataFrame(gap), pd.DataFrame(intr)
    rt = args.rt_bps / 1e4
    print(f"symbols={G.shape[1]}  days={len(G)}  k={args.k}/leg  rt_cost={args.rt_bps}bps\n")

    # --- top/bottom-k gap fade (long biggest gap-downs, short biggest gap-ups) ---
    sp = []
    for d in G.index:
        g = G.loc[d].dropna(); f = I.loc[d]
        common = g.index.intersection(f.dropna().index)
        if len(common) < 2 * args.k:
            continue
        g = g[common].sort_values()
        longs, shorts = g.index[: args.k], g.index[-args.k:]
        sp.append(f[longs].mean() - f[shorts].mean())
    print("k-based (trades every day):")
    stats_line(np.array(sp), rt, f"long{args.k}/short{args.k}")

    # --- threshold variants: only trade names with |gap| > cut ---
    print("\nthreshold (only large gaps; long gap<-c, short gap>+c):")
    for cut in (0.01, 0.02, 0.03):
        sp = []
        for d in G.index:
            g = G.loc[d].dropna(); f = I.loc[d]
            common = g.index.intersection(f.dropna().index)
            g = g[common]; f = f[common]
            longs = g[g < -cut].index; shorts = g[g > cut].index
            if len(longs) == 0 and len(shorts) == 0:
                continue
            r = 0.0
            if len(longs): r += f[longs].mean()
            if len(shorts): r -= f[shorts].mean()
            sp.append(r / (1 if (len(longs) and len(shorts)) else 1))
        stats_line(np.array(sp), rt, f"|gap|>{cut*100:.0f}%")


if __name__ == "__main__":
    main()
