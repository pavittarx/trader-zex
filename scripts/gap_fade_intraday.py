"""Intraday gap-fade backtest on real intraday bars (realistic fills + cost).

Tests the GAP_FADE_THESIS with proper entry/exit timing instead of the daily-bar
open-print proxy. Each trading day:

  gap_i      = day_open / prev_day_close - 1            (known at the open)
  pick legs  = LONG biggest gap-downs, SHORT biggest gap-ups (top/bottom-k)
  entry_px   = close of the bar `entry_offset` bars after the open
  exit_px    = close of the bar `exit_offset` bars before the session close
  leg P&L    = (exit/entry - 1) for longs, (entry/exit - 1) for shorts
             - round-trip cost per leg

Sweeps entry/exit timing so we can see whether waiting past the open auction
improves fills. No look-ahead: the gap is fixed at the open; entry never uses
a price before the entry bar.
"""
from __future__ import annotations

import argparse
import time
from datetime import date, timedelta

import numpy as np
import pandas as pd

import config  # noqa
from fyers_client import FyersClient
import logging
logging.disable(logging.WARNING)


def fetch_intraday(client: FyersClient, sym: str, frm: date, to: date,
                   resolution: str = "15", chunk_days: int = 95) -> pd.DataFrame:
    """Fetch intraday bars in <=chunk_days windows (Fyers intraday request cap)."""
    parts = []
    cur = frm
    while cur <= to:
        end = min(cur + timedelta(days=chunk_days - 1), to)
        try:
            df = client.get_history(sym, resolution, date_from=cur, date_to=end)
            if not df.empty:
                parts.append(df)
        except Exception:
            pass
        cur = end + timedelta(days=1)
        time.sleep(config.API_SLEEP_SECONDS)
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts).sort_index()[~pd.concat(parts).sort_index().index.duplicated()]


def day_prices(intraday: pd.DataFrame, entry_off: int, exit_off: int) -> pd.DataFrame:
    """Per-day open, prev_close, entry_px, exit_px from intraday bars."""
    g = intraday.copy()
    g["d"] = g.index.normalize()
    rows = []
    for d, bars in g.groupby("d"):
        bars = bars.sort_index()
        if len(bars) < max(entry_off + 1, exit_off + 1) + 1:
            continue
        # entry_off == -1 => fill at the 9:15 open-auction print (the daily-proxy,
        # generally unreachable in practice); >=0 => close of that many bars after open.
        entry_px = bars["open"].iloc[0] if entry_off < 0 else bars["close"].iloc[entry_off]
        rows.append({
            "d": d,
            "open": bars["open"].iloc[0],
            "day_close": bars["close"].iloc[-1],
            "entry_px": entry_px,
            "exit_px": bars["close"].iloc[-(exit_off + 1)],     # bar before close
        })
    df = pd.DataFrame(rows).set_index("d")
    df["prev_close"] = df["day_close"].shift(1)
    df["gap"] = df["open"] / df["prev_close"] - 1
    return df.dropna(subset=["prev_close"])


def run(panel: dict[str, pd.DataFrame], k: int, rt_bps: float,
        entry_off: int, exit_off: int, direction: str = "fade") -> dict | None:
    per_sym = {s: day_prices(df, entry_off, exit_off) for s, df in panel.items()}
    gap = pd.DataFrame({s: d["gap"] for s, d in per_sym.items()})
    # intraday leg return entry->exit, per symbol per day
    eret = pd.DataFrame({s: d["exit_px"] / d["entry_px"] - 1 for s, d in per_sym.items()})
    rt = rt_bps / 1e4

    daily = []
    for d in gap.index:
        g = gap.loc[d].dropna()
        r = eret.loc[d]
        common = g.index.intersection(r.dropna().index)
        if len(common) < 2 * k:
            continue
        g = g[common].sort_values()
        # fade: long gap-downs (low g), short gap-ups (high g).
        # momentum: the opposite — long gap-ups, short gap-downs.
        low, high = g.index[:k], g.index[-k:]
        longs, shorts = (low, high) if direction == "fade" else (high, low)
        pnl = r[longs].mean() - r[shorts].mean() - rt   # one round trip / leg / day
        daily.append(pnl)
    if len(daily) < 20:
        return None
    a = np.array(daily)
    ann = ((1 + a.mean()) ** 252 - 1) * 100
    t = a.mean() / (a.std() / np.sqrt(len(a))) if a.std() > 0 else 0.0
    sharpe = (a.mean() / a.std()) * np.sqrt(252) if a.std() > 0 else 0.0
    return {"net_ann": ann, "t": t, "sharpe": sharpe, "win": (a > 0).mean() * 100, "days": len(a)}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", required=True)
    p.add_argument("--date-from", type=date.fromisoformat, required=True)
    p.add_argument("--date-to", type=date.fromisoformat, default=date.today())
    p.add_argument("--resolution", default="15")
    p.add_argument("--k", type=int, default=3)
    p.add_argument("--rt-bps", type=float, default=15.0)
    p.add_argument("--direction", choices=("fade", "momentum"), default="fade")
    args = p.parse_args()

    client = FyersClient()
    panel = {}
    for s in args.symbols:
        df = fetch_intraday(client, s, args.date_from, args.date_to, args.resolution)
        if not df.empty and df.index.normalize().nunique() > 20:
            panel[s] = df
    print(f"symbols={len(panel)}  res={args.resolution}m  k={args.k}  rt={args.rt_bps}bps")
    if len(panel) < 2 * args.k:
        print("Not enough symbols for the chosen k."); return

    print(f"\n{'entry':>12}{'exit':>14}{'net_ann%':>10}{'t':>7}{'Sharpe':>8}{'win%':>6}{'days':>6}")
    # eo=-1: fill at 9:15 open-auction print (daily proxy / control).
    # eo>=0: enter at close of that many bars after the open (realistic). (15m bars: 1≈+15min)
    print(f"direction={args.direction}")
    for eo in (-1, 0, 1, 2):
        for xo in (0, 1):
            r = run(panel, args.k, args.rt_bps, eo, xo, args.direction)
            if r:
                etxt = "open(auction)" if eo < 0 else ("open" if eo == 0 else f"open+{eo*int(args.resolution)}m")
                xtxt = "close" if xo == 0 else f"close-{xo*int(args.resolution)}m"
                print(f"{etxt:>12}{xtxt:>14}{r['net_ann']:>10.1f}{r['t']:>+7.2f}"
                      f"{r['sharpe']:>+8.2f}{r['win']:>5.0f}%{r['days']:>6}")


if __name__ == "__main__":
    main()
