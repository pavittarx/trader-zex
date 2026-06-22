"""Phase 3 test: walk-forward cadence comparison after costs.

Compares weekly/monthly/quarterly rebalance on train/validate/test splits
using the same PIT-aware signal stack.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from strategies.momentum.research.prepare_data import prepare_data
from strategies.momentum.signal import get_target_portfolio, load_or_compute_signals


@dataclass(frozen=True)
class Split:
    name: str
    start: date
    end: date


def _friday_on_or_after(d: date) -> date:
    cur = d
    while cur.weekday() != 4:
        cur += timedelta(days=1)
    return cur


def _simulate_period(
    universe_data: dict[str, pd.DataFrame],
    signals: pd.DataFrame,
    split: Split,
    rebalance_days: int,
    top_pct: float = 0.20,
    turnover_gate: float = 0.015,
    entry_bps: float = 30.0,
    exit_bps: float = 30.0,
) -> dict:
    rebalance_dates: list[date] = []
    d = _friday_on_or_after(split.start)
    while d <= split.end:
        rebalance_dates.append(d)
        d += timedelta(days=rebalance_days)

    current_portfolio: set[str] = set()
    returns: list[float] = []
    trade_count = 0
    skips = 0

    for rebal_date in rebalance_dates:
        rebal_ts = pd.Timestamp(rebal_date)
        if rebal_ts not in signals.index:
            continue
        target = get_target_portfolio(signals, rebal_ts, top_pct=top_pct)
        if not target:
            continue
        to_add = target - current_portfolio
        to_remove = current_portfolio - target
        turnover = len(to_add | to_remove) / max(len(current_portfolio), 1) if current_portfolio else 1.0
        if turnover < turnover_gate:
            skips += 1
            continue
        trade_count += len(to_add) + len(to_remove)

        next_ts = pd.Timestamp(rebal_date + timedelta(days=rebalance_days))
        fwd_returns: list[float] = []
        for symbol in target:
            df = universe_data.get(symbol)
            if df is None:
                continue
            entry = df[(df.index > rebal_ts) & (df.index <= rebal_ts + pd.Timedelta(days=4))]
            exit_ = df[(df.index > next_ts) & (df.index <= next_ts + pd.Timedelta(days=4))]
            if len(entry) == 0 or len(exit_) == 0:
                continue
            entry_px = ((entry["open"] + entry["high"] + entry["low"] + entry["close"]) / 4).iloc[-1]
            exit_px = ((exit_["open"] + exit_["high"] + exit_["low"] + exit_["close"]) / 4).iloc[-1]
            if entry_px <= 0:
                continue
            fwd_returns.append(float((exit_px - entry_px) / entry_px))
        if not fwd_returns:
            continue

        gross = float(np.mean(fwd_returns))
        churn_ratio = (len(to_add) + len(to_remove)) / max(len(target), 1)
        cost_drag = ((entry_bps + exit_bps) / 10000.0) * churn_ratio
        returns.append(gross - cost_drag)
        current_portfolio = target

    r = np.asarray(returns, dtype=float)
    if len(r) == 0:
        return {"n_rebalances": 0, "sharpe": 0.0, "annual_return": 0.0, "annual_vol": 0.0, "win_rate": 0.0, "trades": trade_count, "turnover_skips": skips}

    periods_per_year = 252 / rebalance_days
    years = len(r) / periods_per_year
    total_ret = float(np.prod(1 + r) - 1)
    annual_ret = float((1 + total_ret) ** (1 / years) - 1) if years > 0 else 0.0
    annual_vol = float(np.std(r) * np.sqrt(periods_per_year))
    sharpe = float((np.mean(r) / np.std(r)) * np.sqrt(periods_per_year)) if np.std(r) > 0 else 0.0
    win_rate = float((r > 0).sum() / len(r))
    return {
        "n_rebalances": int(len(r)),
        "sharpe": round(sharpe, 4),
        "annual_return": round(annual_ret, 4),
        "annual_vol": round(annual_vol, 4),
        "win_rate": round(win_rate, 4),
        "trades": int(trade_count),
        "turnover_skips": int(skips),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--date-from", default="2015-01-01")
    p.add_argument("--date-to", default="2024-06-30")
    p.add_argument("--n-symbols", type=int, default=50)
    args = p.parse_args()

    date_from = datetime.strptime(args.date_from, "%Y-%m-%d").date()
    date_to = datetime.strptime(args.date_to, "%Y-%m-%d").date()

    universe_data = prepare_data(date_from, date_to, n_symbols=args.n_symbols, force_refetch=False)
    signals = load_or_compute_signals(universe_data, date_from, date_to, force_recompute=False)

    splits = [
        Split("TRAIN", date(2015, 1, 1), date(2015, 12, 31)),
        Split("VALIDATE", date(2016, 1, 1), date(2019, 12, 31)),
        Split("TEST", date(2020, 1, 1), date_to),
    ]
    cadences = {"weekly": 7, "monthly": 21, "quarterly": 63}

    out: dict[str, dict[str, dict]] = {}
    for name, days in cadences.items():
        out[name] = {}
        for split in splits:
            out[name][split.name] = _simulate_period(universe_data, signals, split, rebalance_days=days)

    summary: dict[str, float] = {}
    for name in cadences:
        val = out[name]["VALIDATE"]["sharpe"]
        test = out[name]["TEST"]["sharpe"]
        summary[name] = round((val + test) / 2.0, 4)

    best = max(summary, key=summary.get)
    payload = {
        "splits": [
            {"name": s.name, "start": s.start.isoformat(), "end": s.end.isoformat()}
            for s in splits
        ],
        "results": out,
        "selection_score": summary,
        "best_cadence": best,
    }

    out_dir = Path(f"~/.trader_zex/backtests/momentum/{date_from}_{date_to}").expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "phase3_walkforward_cadence.json"
    out_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
