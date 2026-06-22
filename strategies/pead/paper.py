"""PEAD paper-trade runner (Phase 4).

One cycle:
1) fetch latest daily bars for locked universe
2) detect reaction-day entries (post-earnings)
3) evaluate exits (corp-action guard, stop, hold horizon)
4) persist paper positions/trades
5) evaluate kill-switch on realized exits
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from core.live import state as state_store
from core.live.risk import build_killswitch
from core.research.data import fetch_daily
from core.research.event_study import reaction_events
from core.research.events_nse import result_dates
from runners._common import broker_for
from strategies.pead.config import PEADConfig
from strategies.pead.manifest import MANIFEST


def _positions_path(profile: str) -> Path:
    return Path(f"~/.trader_zex/state/pead_{profile}_positions.json").expanduser()


@dataclass
class PaperPosition:
    symbol: str
    qty: float
    entry_price: float
    entry_date: str
    bars_held: int


def _load_positions(path: Path) -> dict[str, PaperPosition]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text())
    out: dict[str, PaperPosition] = {}
    for sym, p in payload.items():
        out[sym] = PaperPosition(
            symbol=sym,
            qty=float(p["qty"]),
            entry_price=float(p["entry_price"]),
            entry_date=str(p["entry_date"]),
            bars_held=int(p["bars_held"]),
        )
    return out


def _save_positions(pos: dict[str, PaperPosition], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        s: {
            "qty": p.qty,
            "entry_price": p.entry_price,
            "entry_date": p.entry_date,
            "bars_held": p.bars_held,
        }
        for s, p in pos.items()
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _close_pair(df: pd.DataFrame, as_of: pd.Timestamp) -> tuple[float, float] | None:
    rows = df[df.index <= as_of]
    if len(rows) < 2:
        return None
    prev_close = float(rows["close"].iloc[-2])
    close = float(rows["close"].iloc[-1])
    if prev_close <= 0 or close <= 0:
        return None
    return prev_close, close


def run_paper_cycle(
    as_of: date,
    lookback_days: int = 800,
    state_name: str = "pead-paper",
    profile: str = "paper",
    market_client=None,
    execution_client=None,
) -> dict:
    cfg = PEADConfig()
    strategy_name = state_name
    st = state_store.load(strategy_name)
    if st.halted:
        raise RuntimeError(
            f"{strategy_name} is HALTED ({st.halted_reason} @ {st.halted_at}). "
            f"Reset with: uv run python -m core.live.monitor {strategy_name} --reset-halt"
        )

    adapter = market_client.adapter if market_client is not None else broker_for(MANIFEST)
    frm = as_of - timedelta(days=lookback_days)
    as_of_ts = pd.Timestamp(as_of)
    universe_data: dict[str, pd.DataFrame] = {}
    events_by_symbol: dict[str, dict[str, float]] = {}

    for sym in cfg.universe:
        dates = result_dates(sym.replace("NSE:", "").replace("-EQ", ""))
        if not dates:
            continue
        df = fetch_daily(adapter, sym, frm, as_of, venue=adapter.venue)
        if df.empty or len(df) < 40:
            continue
        df = df.sort_index()
        df.index = pd.to_datetime(df.index).normalize()
        ev = reaction_events(df["close"], dates, frm)
        universe_data[sym] = df
        events_by_symbol[sym] = ev

    positions_path = _positions_path(profile)
    positions = _load_positions(positions_path)
    trades: list[dict] = []
    closed = 0

    # Evaluate exits on open positions first.
    for sym in sorted(list(positions.keys())):
        df = universe_data.get(sym)
        if df is None:
            continue
        pair = _close_pair(df, as_of_ts)
        if pair is None:
            continue
        prev_close, close = pair
        pos = positions[sym]
        pos.bars_held += 1

        reason = None
        if abs(close / prev_close - 1) > cfg.corp_gap:
            reason = "CORP_ACTION_GUARD"
        elif close <= pos.entry_price * (1 - cfg.stop_pct):
            reason = "STOP"
        elif pos.bars_held >= cfg.hold_bars:
            reason = "HOLD_EXIT"

        if reason is not None:
            rt_cost = cfg.cost_model()["round_trip_bps"] / 10000.0
            net_ret = (close - pos.entry_price) / pos.entry_price - rt_cost
            st.record_trade(as_of.isoformat(), sym, float(net_ret))
            trades.append(
                {
                    "date": as_of.isoformat(),
                    "symbol": sym,
                    "side": "SELL",
                    "qty": round(pos.qty, 6),
                    "price": round(close, 4),
                    "reason": reason,
                    "net_ret": round(net_ret, 6),
                }
            )
            if execution_client is not None:
                execution_client.record_fill(state_name, sym, "SELL", pos.qty, close)
            del positions[sym]
            closed += 1

    # Entries: reaction day and threshold pass.
    capital = cfg.initial_capital * (cfg.paper_trade_size_pct / 100.0)
    gross_now = len(positions) * cfg.alloc_pct
    for sym in sorted(cfg.universe):
        if sym in positions:
            continue
        df = universe_data.get(sym)
        if df is None:
            continue
        pair = _close_pair(df, as_of_ts)
        if pair is None:
            continue
        _, close = pair
        react = events_by_symbol.get(sym, {}).get(as_of.isoformat())
        if react is None or react < cfg.thresh:
            continue
        if gross_now + cfg.alloc_pct > cfg.max_gross:
            continue
        qty = (capital * cfg.alloc_pct) / close if close > 0 else 0.0
        if qty <= 0:
            continue
        positions[sym] = PaperPosition(
            symbol=sym,
            qty=float(qty),
            entry_price=float(close),
            entry_date=as_of.isoformat(),
            bars_held=0,
        )
        trades.append(
            {
                "date": as_of.isoformat(),
                "symbol": sym,
                "side": "BUY",
                "qty": round(qty, 6),
                "price": round(close, 4),
                "reaction": round(float(react), 6),
            }
        )
        if execution_client is not None:
            execution_client.record_fill(state_name, sym, "BUY", qty, close)
        gross_now += cfg.alloc_pct

    _save_positions(positions, positions_path)
    reason = build_killswitch(MANIFEST).check(st.net_returns)
    if reason:
        st.halt(reason)
    state_store.save(st)

    cfg.log_dir.mkdir(parents=True, exist_ok=True)
    trades_path = cfg.log_dir / f"{profile}_trades.csv"
    pd.DataFrame(trades).to_csv(
        trades_path,
        index=False,
        mode="a" if trades_path.exists() else "w",
        header=not trades_path.exists(),
    )

    report = {
        "as_of": as_of.isoformat(),
        "universe_total": len(cfg.universe),
        "universe_loaded": len(universe_data),
        "positions_open": len(positions),
        "trades_written": len(trades),
        "closed_trades_recorded": closed,
        "halted": st.halted,
        "halt_reason": st.halted_reason,
        "trades_log": str(trades_path),
        "positions_state": str(positions_path),
    }
    report_path = cfg.log_dir / f"{profile}_last_run.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    observer = getattr(market_client, "observer", None)
    if observer is not None:
        observer.event(
            "strategy_cycle",
            strategy=state_name,
            profile=profile,
            as_of=report["as_of"],
            universe_loaded=report["universe_loaded"],
            trades_written=report["trades_written"],
            closed_trades_recorded=report["closed_trades_recorded"],
            halted=report["halted"],
        )
    return report


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--as-of", type=str, default=None, help="YYYY-MM-DD (default: today)")
    p.add_argument("--lookback-days", type=int, default=800)
    p.add_argument("--state-name", type=str, default="pead-paper")
    p.add_argument("--profile", type=str, default="paper", help="storage profile (paper/sandbox)")
    args = p.parse_args(argv)

    as_of = (
        datetime.strptime(args.as_of, "%Y-%m-%d").date()
        if args.as_of
        else date.today()
    )
    result = run_paper_cycle(
        as_of=as_of,
        lookback_days=args.lookback_days,
        state_name=args.state_name,
        profile=args.profile,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
