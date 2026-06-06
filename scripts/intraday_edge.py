"""Test intraday/daily edge hypotheses derivable from daily OHLC (cheap):

  H1 Gap fade: does the overnight gap (open/prev_close-1) predict the intraday
     return (close/open-1)? Negative cross-sectional IC => gaps fade.
  H2 Overnight vs intraday decomposition: is the close->open (overnight) return
     systematically different from the open->close (intraday) return?

No intraday bars needed — open/high/low/close per day is enough.
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


def ann_tstat(daily: pd.Series):
    d = daily.dropna()
    if len(d) < 20:
        return None
    ann = ((1 + d.mean()) ** 252 - 1) * 100
    t = d.mean() / (d.std() / np.sqrt(len(d))) if d.std() > 0 else 0.0
    return ann, t, (d > 0).mean() * 100, len(d)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", required=True)
    p.add_argument("--date-from", type=date.fromisoformat, required=True)
    p.add_argument("--date-to", type=date.fromisoformat, default=date.today())
    args = p.parse_args()

    client = FyersClient()
    gap, intraday, overnight = {}, {}, {}
    for s in args.symbols:
        try:
            df = client.get_history(s, "D", date_from=args.date_from, date_to=args.date_to)
            if df.empty or len(df) < 30:
                continue
            df = df.sort_index()
            gap[s] = df["open"] / df["close"].shift() - 1      # overnight (close->open)
            intraday[s] = df["close"] / df["open"] - 1          # session (open->close)
            overnight[s] = gap[s]
        except Exception:
            pass

    if len(gap) < 5:
        print(f"Only {len(gap)} symbols."); return
    G = pd.DataFrame(gap); I = pd.DataFrame(intraday)
    print(f"symbols={G.shape[1]}  days={len(G)}")

    # --- H1: gap-fade cross-sectional IC (gap vs same-day intraday return) ---
    ics = []
    for d in G.index:
        a, b = G.loc[d], I.loc[d]
        common = a.dropna().index.intersection(b.dropna().index)
        if len(common) >= 5:
            ic, _ = stats.spearmanr(a[common], b[common])
            if not np.isnan(ic):
                ics.append(ic)
    ics = np.array(ics)
    t = ics.mean() / (ics.std() / np.sqrt(len(ics))) if len(ics) > 1 and ics.std() > 0 else 0.0
    print("\nH1 gap-fade  IC(gap -> intraday return):")
    print(f"   mean_IC={ics.mean():+.4f}  t={t:+.2f}  days={len(ics)}  "
          f"(negative = gaps fade)")

    # --- H2: overnight vs intraday return decomposition (equal-weight basket) ---
    ov = ann_tstat(pd.DataFrame(overnight).mean(axis=1))
    inn = ann_tstat(I.mean(axis=1))
    print("\nH2 decomposition (equal-weight basket, annualized):")
    if ov:
        print(f"   overnight (close->open): {ov[0]:+7.1f}%  t={ov[1]:+.2f}  up%={ov[2]:.0f}")
    if inn:
        print(f"   intraday  (open->close): {inn[0]:+7.1f}%  t={inn[1]:+.2f}  up%={inn[2]:.0f}")
    print("\n(Buy-and-hold = overnight + intraday combined. If overnight >> intraday,")
    print(" a close->open hold captures the premium and sits out the session.)")


if __name__ == "__main__":
    main()
