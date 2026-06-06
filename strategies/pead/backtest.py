"""PEAD NT backtest entry point — invoked via `python -m runners.backtest pead`.

Runs PEADStrategy (the one NT Strategy class, backtest/live parity) through
the BacktestEngine on daily bars, precomputing each symbol's earnings-reaction
events. Defaults to the locked manifest universe.
"""
from __future__ import annotations

import argparse
import logging
from datetime import date, timedelta

from core import config  # noqa
from core.research.data import fetch_daily
from core.research.event_study import in_bucket, reaction_events, tercile_bounds
from core.research.events_nse import result_dates
from core.backtest.engine import build_engine, _get_positions_report
from core.backtest.instruments import make_equity
from core.backtest.data_loader import make_bar_type, df_to_bars
from core.backtest.metrics import _from_positions

from strategies.pead.manifest import MANIFEST
from strategies.pead.strategy import PEADStrategy, PEADStrategyConfig

logging.disable(logging.WARNING)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="runners.backtest pead")
    p.add_argument("--symbols", nargs="+", default=MANIFEST.universe)
    p.add_argument("--years", type=float, default=2.0)
    p.add_argument("--liq-bucket", choices=("all", "low"), default="all")
    args = p.parse_args(argv)

    from runners._common import broker_for
    adapter = broker_for(MANIFEST)
    to = date.today()
    frm = to - timedelta(days=int(args.years * 365) + 40)

    loaded = []
    for s in args.symbols:
        dates = result_dates(s.replace("NSE:", "").replace("-EQ", ""))
        if not dates:
            continue
        df = fetch_daily(adapter, s, frm, to, venue=adapter.venue)
        if df.empty or len(df) < 60:
            continue
        df = df.sort_index()
        df.index = df.index.normalize()
        ev = reaction_events(df["close"], dates, frm)
        if not ev:
            continue
        liq = float((df["close"] * df["volume"]).median())
        loaded.append((s, df, ev, liq))

    if args.liq_bucket != "all" and loaded:
        bounds = tercile_bounds(x[3] for x in loaded)
        loaded = [x for x in loaded if in_bucket(x[3], bounds, args.liq_bucket)]

    if not loaded:
        print("No symbols with events.")
        return

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
