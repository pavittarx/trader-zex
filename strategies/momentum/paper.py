"""Momentum paper-trade runner (Phase 4).

Simulates a live rebalance cycle:
1) fetch latest available bars
2) compute PIT-aware momentum signal
3) generate target portfolio
4) apply turnover gate
5) simulate VWAP fills and persist paper positions/trades
6) evaluate kill-switch on realized exits
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
from strategies.momentum import manifest
from strategies.momentum.config import MomentumConfig
from strategies.momentum.research.prepare_data import prepare_data
from strategies.momentum.signal import get_target_portfolio, load_or_compute_signals


POSITIONS_PATH = Path("~/.trader_zex/state/momentum_paper_positions.json").expanduser()


def _positions_path(profile: str) -> Path:
    return Path(f"~/.trader_zex/state/momentum_{profile}_positions.json").expanduser()


@dataclass
class PaperPosition:
    symbol: str
    qty: float
    avg_price: float
    entry_date: str


def _load_positions(path: Path) -> dict[str, PaperPosition]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text())
    out: dict[str, PaperPosition] = {}
    for symbol, p in raw.items():
        out[symbol] = PaperPosition(
            symbol=symbol,
            qty=float(p["qty"]),
            avg_price=float(p["avg_price"]),
            entry_date=str(p["entry_date"]),
        )
    return out


def _save_positions(pos: dict[str, PaperPosition], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        s: {"qty": p.qty, "avg_price": p.avg_price, "entry_date": p.entry_date}
        for s, p in pos.items()
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _nearest_vwap(df: pd.DataFrame, as_of: pd.Timestamp) -> float | None:
    row = df[df.index <= as_of]
    if len(row) == 0:
        return None
    r = row.iloc[-1]
    return float((r["open"] + r["high"] + r["low"] + r["close"]) / 4.0)


def run_paper_cycle(
    as_of: date,
    n_symbols: int,
    lookback_days: int,
    state_name: str = "momentum-paper",
    profile: str = "paper",
    market_client=None,
    execution_client=None,
) -> dict:
    cfg = MomentumConfig()
    ks_state = state_store.load(state_name)
    if ks_state.halted:
        raise RuntimeError(
            f"{state_name} is HALTED ({ks_state.halted_reason} @ {ks_state.halted_at}). "
            f"Reset with: uv run python -m core.live.monitor {state_name} --reset-halt"
        )

    date_from = as_of - timedelta(days=lookback_days)
    raw_client = getattr(market_client, "raw_client", None)
    universe_data = prepare_data(
        date_from,
        as_of,
        n_symbols=n_symbols,
        force_refetch=False,
        client=raw_client,
    )
    signals = load_or_compute_signals(universe_data, date_from, as_of, force_recompute=False)
    if signals.empty:
        raise RuntimeError("No signals available for paper cycle.")

    valid_dates = signals.index[signals.index <= pd.Timestamp(as_of)]
    if len(valid_dates) == 0:
        raise RuntimeError(f"No signal date <= {as_of}.")
    signal_date = pd.Timestamp(valid_dates.max())

    target = get_target_portfolio(signals, signal_date, top_pct=0.20)
    if not target:
        raise RuntimeError(f"No target portfolio on {signal_date.date()}.")

    positions_path = _positions_path(profile)
    positions = _load_positions(positions_path)
    current = set(positions.keys())
    to_add = target - current
    to_remove = current - target
    turnover = len(to_add | to_remove) / max(len(current), 1) if current else 1.0
    gate = cfg.turnover_threshold_pct / 100.0

    trades: list[dict] = []
    closed_count = 0
    cost_bps = cfg.cost_model().get("round_trip_bps", 35)

    if turnover >= gate:
        # Exit removed symbols.
        for symbol in sorted(to_remove):
            pos = positions[symbol]
            if symbol not in universe_data:
                continue
            px = _nearest_vwap(universe_data[symbol], signal_date)
            if px is None:
                continue
            ret = (px - pos.avg_price) / pos.avg_price - (cost_bps / 10000.0)
            ks_state.record_trade(signal_date.date().isoformat(), symbol, float(ret))
            trades.append(
                {
                    "date": signal_date.date().isoformat(),
                    "symbol": symbol,
                    "side": "SELL",
                    "qty": pos.qty,
                    "price": round(px, 4),
                    "net_ret": round(ret, 6),
                }
            )
            if execution_client is not None:
                execution_client.record_fill(state_name, symbol, "SELL", pos.qty, float(px))
            del positions[symbol]
            closed_count += 1

        # Enter added symbols as equal-notional paper allocations.
        capital = cfg.initial_capital * (cfg.paper_trade_size_pct / 100.0)
        slot = capital / max(len(target), 1)
        for symbol in sorted(to_add):
            if symbol not in universe_data:
                continue
            px = _nearest_vwap(universe_data[symbol], signal_date)
            if px is None or px <= 0:
                continue
            qty = slot / px
            positions[symbol] = PaperPosition(
                symbol=symbol,
                qty=float(qty),
                avg_price=float(px),
                entry_date=signal_date.date().isoformat(),
            )
            trades.append(
                {
                    "date": signal_date.date().isoformat(),
                    "symbol": symbol,
                    "side": "BUY",
                    "qty": round(float(qty), 6),
                    "price": round(float(px), 4),
                }
            )
            if execution_client is not None:
                execution_client.record_fill(state_name, symbol, "BUY", float(qty), float(px))

    _save_positions(positions, positions_path)
    reason = build_killswitch(manifest.MANIFEST).check(ks_state.net_returns)
    if reason:
        ks_state.halt(reason)
    state_store.save(ks_state)

    cfg.log_dir.mkdir(parents=True, exist_ok=True)
    trades_path = cfg.log_dir / f"{profile}_trades.csv"
    pd.DataFrame(trades).to_csv(
        trades_path,
        index=False,
        mode="a" if trades_path.exists() else "w",
        header=not trades_path.exists(),
    )

    report = {
        "as_of": signal_date.date().isoformat(),
        "n_symbols_data": len(universe_data),
        "target_count": len(target),
        "current_count_before": len(current),
        "current_count_after": len(positions),
        "turnover": round(turnover, 4),
        "turnover_gate": gate,
        "rebalanced": turnover >= gate,
        "to_add": len(to_add),
        "to_remove": len(to_remove),
        "trades_written": len(trades),
        "closed_trades_recorded": closed_count,
        "halted": ks_state.halted,
        "halt_reason": ks_state.halted_reason,
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
            n_symbols_data=report["n_symbols_data"],
            target_count=report["target_count"],
            trades_written=report["trades_written"],
            closed_trades_recorded=report["closed_trades_recorded"],
            halted=report["halted"],
        )
    return report


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", type=str, default=None, help="YYYY-MM-DD (default: today)")
    parser.add_argument("--n-symbols", type=int, default=50)
    parser.add_argument("--lookback-days", type=int, default=900)
    parser.add_argument("--state-name", type=str, default="momentum-paper")
    parser.add_argument("--profile", type=str, default="paper", help="storage profile (paper/sandbox)")
    args = parser.parse_args(argv)

    as_of = (
        datetime.strptime(args.as_of, "%Y-%m-%d").date()
        if args.as_of
        else date.today()
    )
    out = run_paper_cycle(
        as_of=as_of,
        n_symbols=args.n_symbols,
        lookback_days=args.lookback_days,
        state_name=args.state_name,
        profile=args.profile,
    )
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
