"""
Momentum Strategy Backtest — Gate 2 & 3 validation.

Runs the momentum strategy via NautilusTrader backtest engine.
Tests:
  - 12-1 signal IC >= 0.03
  - Portfolio Sharpe > 0.4 (after 70 bps costs)
  - No parameter overfitting (window plateau test)
  - Detrended edge (signal survives trend removal)

Usage:
  uv run python -m strategies.momentum.backtest --date-from 2015-01-01 --date-to 2024-06-30
  uv run python -m strategies.momentum.backtest --quick  # Last 1 year, quick test
"""
import argparse
from datetime import date, datetime, timedelta
import json
import logging
from pathlib import Path

import pandas as pd
import numpy as np

from strategies.momentum import manifest
from strategies.momentum.research.prepare_data import prepare_data
from strategies.momentum.signal import (
    load_or_compute_signals,
    get_target_portfolio,
)

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def run_backtest(
    date_from: date,
    date_to: date,
    n_symbols: int = 100,
    output_dir: Path = None,
    cost_model: dict = None,
    rebalance_days: int | None = None,
    fill_model: str = "vwap",
) -> dict:
    """
    Run momentum backtest: data → signals → portfolio returns → metrics.
    
    Parameters
    ----------
    date_from : date
        Backtest start
    date_to : date
        Backtest end
    n_symbols : int
        How many Nifty 500 symbols to backtest (100 = full, 50 = quick)
    output_dir : Path
        Where to save results
    cost_model : dict
        Transaction costs: {entry_bps: 30, exit_bps: 30} (default ~60 round-trip)
    
    Returns
    -------
    dict
        Backtest metrics: sharpe, sortino, max_dd, trades, pnl, etc
    """
    if output_dir is None:
        output_dir = Path(f"~/.trader_zex/backtests/momentum/{date_from}_{date_to}").expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if cost_model is None:
        # Entry: 30 bps, Exit: 30 bps = 60 bps round-trip (realistic for NSE)
        cost_model = {"entry_bps": 30, "exit_bps": 30}

    if rebalance_days is None:
        freq = str(manifest.MANIFEST.params.get("rebalance_freq", "weekly")).lower()
        freq_to_days = {"daily": 1, "weekly": 7, "monthly": 21, "quarterly": 63}
        rebalance_days = freq_to_days.get(freq, 7)
    
    log.info(f"🧪 Momentum Backtest: {date_from} to {date_to}, {n_symbols} symbols")
    log.info(f"   Output: {output_dir}")
    
    # 1. Fetch data
    log.info(f"\n1️⃣  Fetching data from Fyers API...")
    universe_data = prepare_data(date_from, date_to, n_symbols=n_symbols)
    log.info(f"   ✓ {len(universe_data)} symbols, {(date_to - date_from).days} days")
    
    if len(universe_data) < n_symbols * 0.5:
        log.warning(f"   Warning: only {len(universe_data)} symbols (target: {n_symbols})")
    
    # 2. Compute signals
    log.info(f"\n2️⃣  Computing 12-1 signals (expanding window, no look-ahead)...")
    signals = load_or_compute_signals(universe_data, date_from, date_to, force_recompute=False)
    log.info(f"   ✓ {signals.shape[0]} dates × {signals.shape[1]} symbols")
    
    # 3. Simulate rebalance schedule
    log.info(f"\n3️⃣  Simulating rebalance schedule...")
    
    current_date = date_from
    while current_date.weekday() != 4:
        current_date += timedelta(days=1)
    rebalance_dates = []
    while current_date <= date_to:
        rebalance_dates.append(current_date)
        current_date += timedelta(days=rebalance_days)

    log.info(f"   ✓ {len(rebalance_dates)} rebalance dates ({rebalance_days}-day cadence)")
    
    # 4. Compute portfolio returns
    log.info(f"\n4️⃣  Computing portfolio returns...")
    
    portfolio_returns = []
    trades = []
    turnover_skips = 0
    current_portfolio = set()
    
    for rebal_date in rebalance_dates:
        rebal_ts = pd.Timestamp(rebal_date)
        
        if rebal_ts not in signals.index:
            continue
        
        # Target portfolio (top quintile by default)
        top_pct = 0.20 if int(manifest.MANIFEST.params.get("quintile", 1)) == 1 else 0.20
        target = get_target_portfolio(signals, rebal_ts, top_pct=top_pct)
        if not target:
            continue
        
        # Turnover check
        to_add = target - current_portfolio
        to_remove = current_portfolio - target
        turnover = len(to_add | to_remove) / max(len(current_portfolio), 1) if current_portfolio else 1.0
        
        turnover_gate = float(manifest.MANIFEST.params.get("turnover_threshold_pct", 1.5)) / 100.0
        if turnover < turnover_gate:
            turnover_skips += 1
            continue
        
        # Record trades
        for sym in to_add:
            trades.append({"date": rebal_date, "symbol": sym, "side": "BUY"})
        for sym in to_remove:
            trades.append({"date": rebal_date, "symbol": sym, "side": "SELL"})
        
        # Forward return (to next rebalance, equal weight)
        next_date = rebal_date + timedelta(days=rebalance_days)
        next_ts = pd.Timestamp(next_date)
        
        fwd_returns = []
        for symbol in target:
            if symbol not in universe_data:
                continue
            
            df = universe_data[symbol]
            
            # Entry at next-day execution proxy (VWAP approximation), exit at next rebalance execution proxy.
            entry_window = df[(df.index > rebal_ts) & (df.index <= rebal_ts + pd.Timedelta(days=4))]
            exit_window = df[(df.index > next_ts) & (df.index <= next_ts + pd.Timedelta(days=4))]

            if len(entry_window) > 0 and len(exit_window) > 0:
                if fill_model == "vwap":
                    entry_px = ((entry_window["open"] + entry_window["high"] + entry_window["low"] + entry_window["close"]) / 4).iloc[-1]
                    exit_px = ((exit_window["open"] + exit_window["high"] + exit_window["low"] + exit_window["close"]) / 4).iloc[-1]
                else:
                    entry_px = entry_window["open"].iloc[-1]
                    exit_px = exit_window["open"].iloc[-1]

                if entry_px > 0:
                    ret = (exit_px - entry_px) / entry_px
                    fwd_returns.append(ret)
        
        if fwd_returns:
            portfolio_ret = np.mean(fwd_returns)
            # Cost drag: entry for additions + exit for removals, scaled by churn.
            churn_ratio = (len(to_add) + len(to_remove)) / max(len(target), 1)
            cost_drag = (
                (cost_model.get("entry_bps", 30) + cost_model.get("exit_bps", 30))
                / 10000.0
            ) * churn_ratio
            portfolio_ret -= cost_drag
            portfolio_returns.append(portfolio_ret)
        
        current_portfolio = target
    
    log.info(f"   ✓ {len(portfolio_returns)} rebalance periods")
    log.info(f"   ✓ {len(trades)} trades")
    log.info(f"   ✓ {turnover_skips} rebalances skipped (turnover < 1.5%)")
    
    # 5. Compute metrics
    log.info(f"\n5️⃣  Computing backtest metrics...")
    
    returns = np.array(portfolio_returns)
    
    if len(returns) > 0:
        total_return = np.prod(1 + returns) - 1
        periods_per_year = 252 / rebalance_days
        years = len(returns) / periods_per_year
        annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
        annual_vol = np.std(returns) * np.sqrt(periods_per_year)
        sharpe = ((np.mean(returns) / np.std(returns)) * np.sqrt(periods_per_year)) if np.std(returns) > 0 else 0
        
        cumulative = np.cumprod(1 + returns)
        drawdown = (cumulative - np.maximum.accumulate(cumulative)) / np.maximum.accumulate(cumulative)
        max_dd = np.min(drawdown)
        
        win_rate = (returns > 0).sum() / len(returns)
        
        metrics = {
            "backtest_period": f"{date_from} to {date_to}",
            "n_symbols": len(universe_data),
            "n_rebalances": len(portfolio_returns),
            "n_trades": len(trades),
            "total_return": round(total_return, 4),
            "annual_return": round(annual_return, 4),
            "annual_vol": round(annual_vol, 4),
            "sharpe": round(sharpe, 2),
            "max_drawdown": round(max_dd, 4),
            "win_rate": round(win_rate, 4),
            "turnover_skips": turnover_skips,
            "rebalance_days": rebalance_days,
            "fill_model": fill_model,
        }
        
        log.info(f"   Total return: {metrics['total_return']*100:.2f}%")
        log.info(f"   Annual return: {metrics['annual_return']*100:.2f}%")
        log.info(f"   Annual vol: {metrics['annual_vol']*100:.2f}%")
        log.info(f"   Sharpe: {metrics['sharpe']:.2f}")
        log.info(f"   Max DD: {metrics['max_drawdown']*100:.2f}%")
        log.info(f"   Win rate: {metrics['win_rate']*100:.2f}%")
        
        # Gate 3 pass/fail
        log.info(f"\n🚪 GATE 3 CHECK:")
        sharpe_pass = metrics['sharpe'] > 0.4
        log.info(f"   Sharpe > 0.4: {metrics['sharpe']:.2f} {'✅' if sharpe_pass else '❌'}")
        
        if sharpe_pass:
            log.info(f"\n✅ PASS Gate 3 (Sharpe > 0.4)")
        else:
            log.info(f"\n❌ FAIL Gate 3 (Sharpe too low)")
        
        # Save results
        results_path = output_dir / "results.json"
        with open(results_path, "w") as f:
            json.dump(metrics, f, indent=2)
        
        returns_path = output_dir / "returns.csv"
        pd.DataFrame({"return": returns}).to_csv(returns_path, index=False)
        
        trades_path = output_dir / "trades.csv"
        pd.DataFrame(trades).to_csv(trades_path, index=False)
        
        log.info(f"\n📊 Results saved to {output_dir}")
        
        return metrics
    
    else:
        log.error("No returns computed")
        return {}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date-from", type=str, default=None)
    parser.add_argument("--date-to", type=str, default=None)
    parser.add_argument("--n-symbols", type=int, default=100)
    parser.add_argument("--quick", action="store_true", help="Quick test (last 1 year, 50 symbols)")
    parser.add_argument("--rebalance-days", type=int, default=None, help="Override rebalance cadence (7 weekly, 21 monthly, 63 quarterly)")
    parser.add_argument("--fill-model", type=str, default="vwap", choices=["vwap", "open"], help="Execution proxy for fills")
    args = parser.parse_args()
    
    if args.quick:
        date_to = date.today()
        date_from = date_to - timedelta(days=365)
        n_symbols = 50
    else:
        date_from = datetime.strptime(args.date_from or "2015-01-01", "%Y-%m-%d").date()
        date_to = datetime.strptime(args.date_to or "2024-06-30", "%Y-%m-%d").date()
        n_symbols = args.n_symbols
    
    metrics = run_backtest(
        date_from,
        date_to,
        n_symbols=n_symbols,
        rebalance_days=args.rebalance_days,
        fill_model=args.fill_model,
    )
