"""Test a short-term reversal long/short: long yesterday's losers, short winners.

Each rebalance (every h days), rank the universe by prior-day return, go long
the bottom-k and short the top-k, hold h days. Reports the gross spread's
stats AND the break-even round-trip cost — because daily rebalancing is where
reversal edges usually die on costs.
"""
import argparse
from datetime import date

import numpy as np
import pandas as pd
from scipy import stats

from core import config  # noqa
from core.brokers.fyers.client import FyersClient
import logging
logging.disable(logging.WARNING)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", required=True)
    p.add_argument("--date-from", type=date.fromisoformat, required=True)
    p.add_argument("--date-to", type=date.fromisoformat, default=date.today())
    p.add_argument("--k", type=int, default=5, help="names per leg")
    args = p.parse_args()

    client = FyersClient()
    closes = {}
    for s in args.symbols:
        try:
            df = client.get_history(s, "D", date_from=args.date_from, date_to=args.date_to)
            if not df.empty and len(df) > 25:
                closes[s] = df.sort_index()["close"]
        except Exception:
            pass
    if len(closes) < 10:
        print(f"Only {len(closes)} symbols — need a wider universe."); return

    px = pd.DataFrame(closes).dropna(how="all")
    ret1 = px.pct_change(1)            # signal: prior-day return (known at close D)

    print(f"symbols={px.shape[1]}  days={len(px)}  k={args.k}/leg")
    print(f"{'hold':>5}{'gross_ann%':>11}{'t_stat':>8}{'Sharpe':>8}{'win%':>6}{'breakeven_bps':>14}")
    for h in (1, 3, 5):
        fwd = px.shift(-h) / px - 1            # forward h-day return per name
        rebal = range(0, len(px) - h, h)       # non-overlapping rebalances
        spreads = []
        for i in rebal:
            sig = ret1.iloc[i].dropna()
            f = fwd.iloc[i]
            common = sig.index.intersection(f.dropna().index)
            if len(common) < 2 * args.k:
                continue
            sig = sig[common].sort_values()
            longs = sig.index[: args.k]        # biggest losers -> long (reversal)
            shorts = sig.index[-args.k:]       # biggest winners -> short
            spreads.append(float(f[longs].mean() - f[shorts].mean()))
        if len(spreads) < 5:
            continue
        s = np.array(spreads)
        n_per_yr = 252 / h
        ann = ((1 + s.mean()) ** n_per_yr - 1) * 100
        t = s.mean() / (s.std() / np.sqrt(len(s))) if s.std() > 0 else 0.0
        sharpe = (s.mean() / s.std()) * np.sqrt(n_per_yr) if s.std() > 0 else 0.0
        win = (s > 0).mean() * 100
        breakeven = s.mean() * 1e4   # bps per rebalance that would zero the gross edge
        print(f"{h:>5}{ann:>11.1f}{t:>+8.2f}{sharpe:>+8.2f}{win:>5.0f}%{breakeven:>14.1f}")
    print("\nReality check: round-trip cost ~30-50 bps/rebalance. Net edge exists "
          "only if breakeven_bps comfortably exceeds that.")


if __name__ == "__main__":
    main()
