"""Portfolio backtest of the PEAD rule — turns the per-event drift into a P&L
stream with an equity curve, Sharpe, and drawdown.

Rule (from PEAD_THESIS.md):
  - Event = earnings reaction day (t+1 after announcement), |reaction| >= thresh.
  - Enter at the reaction-day close: long if reaction up, short if down.
  - Hold H trading days, exit at close. Pay round-trip cost.
  - Equal-weight active book: each trade gets weight 1/target_n of equity,
    so gross exposure is bounded; partial cash when fewer trades are active.

Portfolio daily return = sum over active trades of (close-to-close return * side
* weight), with the round-trip cost applied on the entry day.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta

import numpy as np
import pandas as pd

import config  # noqa
from fyers_client import FyersClient
from scripts.pead_event_ic import fetch_daily, result_dates
import logging
logging.disable(logging.WARNING)


def build_trades(client, symbols, frm, to, thresh, hold):
    """Return (trades, price_panel). Each trade: symbol, entry_pos, exit_pos, side."""
    panel, trades = {}, []
    for s in symbols:
        plain = s.replace("NSE:", "").replace("-EQ", "")
        dates = result_dates(plain)
        if not dates:
            continue
        df = fetch_daily(client, s, frm, to)
        if df.empty or len(df) < 40:
            continue
        close = df.sort_index()["close"]; close.index = close.index.normalize()
        panel[s] = close
        idx = close.index
        for d in dates:
            if d < pd.Timestamp(frm):
                continue
            t = idx.searchsorted(d, side="right")          # reaction day = t+1 (after-hours)
            if t < 1 or t + hold >= len(close):
                continue
            reaction = close.iloc[t] / close.iloc[t - 1] - 1
            if abs(reaction) < thresh:
                continue
            trades.append({"sym": s, "entry": t, "exit": t + hold,
                           "side": 1 if reaction > 0 else -1})
    return trades, panel


def run(trades, panel, target_n, rt_bps):
    """Daily equal-weight book. Returns a date-indexed daily-return series."""
    w = 1.0 / target_n
    rt = rt_bps / 1e4
    # union of all trading dates
    all_dates = sorted(set().union(*[set(c.index) for c in panel.values()]))
    daily = pd.Series(0.0, index=pd.DatetimeIndex(all_dates))
    for tr in trades:
        c = panel[tr["sym"]]
        dates = c.index
        # daily close-to-close returns over the holding window (entry+1 .. exit)
        for j in range(tr["entry"] + 1, tr["exit"] + 1):
            ret = (c.iloc[j] / c.iloc[j - 1] - 1) * tr["side"]
            daily.loc[dates[j]] += ret * w
        # round-trip cost charged once, on the day after entry
        daily.loc[dates[tr["entry"] + 1]] -= rt * w
    return daily


def metrics(daily: pd.Series) -> dict:
    d = daily[daily.index >= daily[daily != 0].index.min()] if (daily != 0).any() else daily
    if len(d) < 20:
        return {}
    eq = (1 + d).cumprod()
    yrs = len(d) / 252
    cagr = eq.iloc[-1] ** (1 / yrs) - 1 if eq.iloc[-1] > 0 else -1
    sharpe = (d.mean() / d.std()) * np.sqrt(252) if d.std() > 0 else 0.0
    dd = (eq / eq.cummax() - 1).min()
    active = (d != 0).mean()
    return {"cagr": cagr * 100, "sharpe": sharpe, "maxdd": dd * 100,
            "final": eq.iloc[-1], "active_days": active * 100, "days": len(d)}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", required=True)
    p.add_argument("--years", type=float, default=2.0)
    p.add_argument("--thresh", type=float, default=0.02, help="min |reaction|")
    p.add_argument("--holds", nargs="+", type=int, default=[1, 20])
    p.add_argument("--target-n", type=int, default=10, help="positions for full investment")
    p.add_argument("--rt-bps", type=float, default=20.0)
    args = p.parse_args()

    client = FyersClient()
    to = date.today(); frm = to - timedelta(days=int(args.years * 365) + 40)
    print(f"thresh=|react|>={args.thresh*100:.0f}%  target_n={args.target_n}  rt={args.rt_bps}bps")
    print(f"\n{'hold':>5}{'trades':>8}{'CAGR%':>9}{'Sharpe':>8}{'maxDD%':>9}{'final_x':>9}{'active%':>9}")
    for h in args.holds:
        trades, panel = build_trades(client, args.symbols, frm, to, args.thresh, h)
        if len(trades) < 20:
            print(f"{h:>5}  too few trades ({len(trades)})"); continue
        m = metrics(run(trades, panel, args.target_n, args.rt_bps))
        if m:
            print(f"{h:>5}{len(trades):>8}{m['cagr']:>+9.1f}{m['sharpe']:>+8.2f}"
                  f"{m['maxdd']:>+9.1f}{m['final']:>9.2f}{m['active_days']:>8.0f}%")
    print("\nNet of cost. Sharpe/CAGR are on the equal-weight active book; active% =")
    print("fraction of days with any position (low = event strategy sits in cash a lot).")


if __name__ == "__main__":
    main()
