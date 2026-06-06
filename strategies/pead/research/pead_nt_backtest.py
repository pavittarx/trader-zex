"""Run PEADStrategy (the NT Strategy) through the real BacktestEngine on daily
bars. Proves the same class that will run live also validates in backtest —
backtest/live parity. Precomputes each symbol's earnings-reaction events.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta

import numpy as np
import pandas as pd

from core import config  # noqa
from core.brokers.fyers.client import FyersClient
from strategies.pead.research.pead_event_ic import fetch_daily, result_dates
from strategies.pead.core import reaction_events, tercile_bounds, in_bucket
from core.backtest.engine import build_engine, _get_positions_report
from core.backtest.instruments import make_equity, fyers_to_instrument_id
from core.backtest.data_loader import make_bar_type, df_to_bars
from strategies.pead.strategy import PEADStrategy, PEADStrategyConfig
from core.backtest.metrics import _from_positions
import logging
logging.disable(logging.WARNING)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", required=True)
    p.add_argument("--years", type=float, default=2.0)
    p.add_argument("--liq-bucket", choices=("all", "low"), default="all")
    args = p.parse_args()

    client = FyersClient()
    to = date.today(); frm = to - timedelta(days=int(args.years * 365) + 40)

    loaded = []
    for s in args.symbols:
        dates = result_dates(s.replace("NSE:", "").replace("-EQ", ""))
        if not dates:
            continue
        df = fetch_daily(client, s, frm, to)
        if df.empty or len(df) < 60:
            continue
        df = df.sort_index(); df.index = df.index.normalize()
        close = df["close"]
        ev = reaction_events(close, dates, frm)
        if not ev:
            continue
        liq = float((df["close"] * df["volume"]).median())
        loaded.append((s, df, ev, liq))

    if args.liq_bucket != "all" and loaded:
        bounds = tercile_bounds(x[3] for x in loaded)
        loaded = [x for x in loaded if in_bucket(x[3], bounds, args.liq_bucket)]

    if not loaded:
        print("No symbols with events."); return

    engine = build_engine(log_level="ERROR")
    for s, df, ev, _ in loaded:
        instrument = make_equity(s)
        engine.add_instrument(instrument)
        bt = make_bar_type(instrument.id, "D")
        engine.add_data(df_to_bars(df, bt, "D"))
        ticker = s.split(":")[-1]
        engine.add_strategy(PEADStrategy(PEADStrategyConfig(
            strategy_id=f"pead-{ticker}",
            instrument_id=str(instrument.id), bar_type=str(bt),
            reaction_events=ev)))

    engine.run()
    report = _get_positions_report(engine)
    m = _from_positions(report) if report is not None else {}
    cap = config.BACKTEST_INITIAL_CAPITAL
    pnl = m.get("total_pnl_inr") or 0.0
    print(f"\n=== PEAD NT backtest ({args.liq_bucket}) ===")
    print(f"symbols={len(loaded)}  trades={0 if report is None else len(report)}")
    print(f"total P&L ₹{pnl:,.0f}  ({pnl/cap*100:+.2f}% on ₹{cap:,.0f})")
    print(f"win% {m.get('win_rate_pct')}  profit_factor {m.get('profit_factor')}  "
          f"maxDD ₹{m.get('max_drawdown_inr')}  cost ₹{m.get('total_cost_inr')}")
    engine.dispose()


if __name__ == "__main__":
    main()
