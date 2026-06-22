"""Gate 5 verification: permutation test, detrended edge, and DSR estimate.

Usage:
  uv run python -m strategies.momentum.research.verify_gate5 --date-from 2015-01-01 --date-to 2024-06-30
"""
from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import kurtosis, norm, skew

from core.research.stats import sharpe
from strategies.momentum.research.prepare_data import prepare_data
from strategies.momentum.signal import get_target_portfolio, load_or_compute_signals

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


@dataclass(frozen=True)
class VerificationConfig:
    rebalance_days: int = 63
    top_pct: float = 0.20
    entry_cost_bps: float = 30.0
    min_turnover: float = 0.015
    permutations: int = 300
    random_seed: int = 7


def _rebalance_dates(start: date, end: date, step_days: int) -> list[date]:
    out: list[date] = []
    d = start
    while d <= end:
        out.append(d)
        d += timedelta(days=step_days)
    return out


def _next_price(df: pd.DataFrame, start_ts: pd.Timestamp, end_ts: pd.Timestamp) -> tuple[float, float] | None:
    at_rebal = df[(df.index >= start_ts - pd.Timedelta(days=1)) & (df.index <= start_ts)]
    forward = df[(df.index > start_ts) & (df.index <= end_ts)]
    if len(at_rebal) == 0 or len(forward) == 0:
        return None
    p0 = float(at_rebal["close"].iloc[-1])
    p1 = float(forward["close"].iloc[-1])
    if p0 <= 0:
        return None
    return p0, p1


def _build_forward_returns(
    universe_data: dict[str, pd.DataFrame],
    rebalance_dates: list[date],
    rebalance_days: int,
) -> dict[pd.Timestamp, dict[str, float]]:
    out: dict[pd.Timestamp, dict[str, float]] = {}
    for d in rebalance_dates:
        d_ts = pd.Timestamp(d)
        n_ts = pd.Timestamp(d + timedelta(days=rebalance_days))
        per_symbol: dict[str, float] = {}
        for symbol, df in universe_data.items():
            px = _next_price(df, d_ts, n_ts)
            if px is None:
                continue
            p0, p1 = px
            per_symbol[symbol] = (p1 - p0) / p0
        if per_symbol:
            out[d_ts] = per_symbol
    return out


def _portfolio_returns(
    signals: pd.DataFrame,
    forward_returns: dict[pd.Timestamp, dict[str, float]],
    cfg: VerificationConfig,
    rng: np.random.Generator | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    strategy: list[float] = []
    market: list[float] = []
    current_portfolio: set[str] = set()

    for d_ts, fwd_map in forward_returns.items():
        if d_ts not in signals.index:
            continue
        available_symbols = set(fwd_map.keys())
        raw_target = get_target_portfolio(signals, d_ts, top_pct=cfg.top_pct)
        if rng is None:
            target = raw_target & available_symbols
        else:
            k = max(1, int(len(available_symbols) * cfg.top_pct))
            target = set(rng.choice(sorted(available_symbols), size=min(k, len(available_symbols)), replace=False))
        if not target:
            continue

        to_add = target - current_portfolio
        to_remove = current_portfolio - target
        turnover = len(to_add | to_remove) / max(len(current_portfolio), 1) if current_portfolio else 1.0
        if turnover < cfg.min_turnover:
            continue

        selected = np.array([fwd_map[s] for s in target], dtype=float)
        if selected.size == 0:
            continue
        gross = float(selected.mean())
        net = gross - (len(to_add) / max(len(target), 1)) * (cfg.entry_cost_bps / 10000.0)
        strategy.append(net)

        broad = np.array(list(fwd_map.values()), dtype=float)
        market.append(float(broad.mean()))
        current_portfolio = target

    return np.asarray(strategy, dtype=float), np.asarray(market, dtype=float)


def _deflated_sharpe_ratio(returns: np.ndarray, num_trials: int) -> float:
    if len(returns) < 5:
        return 0.0
    sr = sharpe(returns, periods=252)
    t = len(returns)
    g3 = float(skew(returns, bias=False))
    g4 = float(kurtosis(returns, fisher=False, bias=False))
    sr_std = np.sqrt(max(1e-12, (1 - g3 * sr + ((g4 - 1) / 4.0) * (sr**2)) / max(t - 1, 1)))
    # Expected max Sharpe under multiple testing (Bailey/Lopez de Prado approximation).
    euler_gamma = 0.5772156649
    z1 = norm.ppf(1 - 1 / max(num_trials, 2))
    z2 = norm.ppf(1 - 1 / (max(num_trials, 2) * np.e))
    sr_star = sr_std * ((1 - euler_gamma) * z1 + euler_gamma * z2)
    z = (sr - sr_star) / sr_std
    return float(norm.cdf(z))


def run_verification(
    date_from: date,
    date_to: date,
    n_symbols: int,
    cfg: VerificationConfig,
    out_dir: Path,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(cfg.random_seed)

    log.info("Preparing universe data")
    universe_data = prepare_data(date_from, date_to, n_symbols=n_symbols, force_refetch=False)
    log.info("Loading momentum signals")
    signals = load_or_compute_signals(universe_data, date_from, date_to, force_recompute=False)

    dates = _rebalance_dates(date_from, date_to, cfg.rebalance_days)
    fwd = _build_forward_returns(universe_data, dates, cfg.rebalance_days)

    real_returns, market_returns = _portfolio_returns(signals, fwd, cfg, rng=None)
    if len(real_returns) == 0:
        raise RuntimeError("No strategy returns were produced for verification window.")

    perm_sharpes: list[float] = []
    for _ in range(cfg.permutations):
        perm_ret, _ = _portfolio_returns(signals, fwd, cfg, rng=rng)
        if len(perm_ret) < 3:
            continue
        perm_sharpes.append(float(sharpe(perm_ret, periods=252)))

    real_sharpe = float(sharpe(real_returns, periods=252))
    detrended = real_returns - market_returns[: len(real_returns)]
    detrended_sharpe = float(sharpe(detrended, periods=252))

    perm_arr = np.asarray(perm_sharpes, dtype=float)
    p_value = float(((perm_arr >= real_sharpe).sum() + 1) / (len(perm_arr) + 1)) if len(perm_arr) else 1.0
    beat_pct = float((real_sharpe > perm_arr).mean() * 100) if len(perm_arr) else 0.0
    dsr = _deflated_sharpe_ratio(real_returns, num_trials=max(cfg.permutations, 1))

    result = {
        "period": f"{date_from} to {date_to}",
        "n_symbols": len(universe_data),
        "rebalance_days": cfg.rebalance_days,
        "n_rebalances": int(len(real_returns)),
        "real_sharpe": round(real_sharpe, 4),
        "detrended_sharpe": round(detrended_sharpe, 4),
        "permutations": int(len(perm_arr)),
        "perm_mean_sharpe": round(float(perm_arr.mean()) if len(perm_arr) else 0.0, 4),
        "perm_p95_sharpe": round(float(np.percentile(perm_arr, 95)) if len(perm_arr) else 0.0, 4),
        "beat_permutation_pct": round(beat_pct, 2),
        "permutation_p_value": round(p_value, 6),
        "dsr_probability": round(dsr, 6),
        "gate_permutation_pass": beat_pct >= 95.0,
        "gate_dsr_pass": dsr > 0.5,
        "gate_detrend_pass": detrended_sharpe > 0.0,
    }

    (out_dir / "gate5_verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    pd.DataFrame({"strategy_return": real_returns, "market_return": market_returns[: len(real_returns)]}).to_csv(
        out_dir / "gate5_returns.csv", index=False
    )
    if len(perm_arr):
        pd.DataFrame({"perm_sharpe": perm_arr}).to_csv(out_dir / "gate5_perm_sharpes.csv", index=False)

    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date-from", type=str, default="2015-01-01")
    parser.add_argument("--date-to", type=str, default="2024-06-30")
    parser.add_argument("--n-symbols", type=int, default=50)
    parser.add_argument("--rebalance-days", type=int, default=63, help="63=quarterly, 21=monthly, 7=weekly")
    parser.add_argument("--permutations", type=int, default=300)
    args = parser.parse_args()

    cfg = VerificationConfig(rebalance_days=args.rebalance_days, permutations=args.permutations)
    date_from = datetime.strptime(args.date_from, "%Y-%m-%d").date()
    date_to = datetime.strptime(args.date_to, "%Y-%m-%d").date()
    out_dir = Path(f"~/.trader_zex/backtests/momentum/{date_from}_{date_to}").expanduser()

    result = run_verification(date_from, date_to, args.n_symbols, cfg, out_dir)
    log.info("Gate 5 verification")
    log.info(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
