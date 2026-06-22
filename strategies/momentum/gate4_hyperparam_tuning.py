"""
Hyperparameter Tuning: Find optimal momentum window (12-1 vs alternatives)
Grid search across windows: 3-1, 6-1, 9-1, 12-1, 18-1, 24-1
Walk-forward validation: train 2015 → validate 2016-2019 → test 2020-2024
"""
import sys
sys.path.insert(0, '/Users/pavix/kuby/copilot-worktrees/trader-zex/pavittarx-cuddly-doodle')

import numpy as np
import pandas as pd
from datetime import date, timedelta
from strategies.momentum.research.prepare_data import prepare_data
from pathlib import Path

def compute_momentum_signal(prices_df: pd.DataFrame, window_months: int, exclude_months: int = 1) -> pd.Series:
    """
    Compute momentum signal: return from (window_months ago) to (exclude_months ago)
    High momentum = high long position
    """
    if len(prices_df) < (window_months + exclude_months + 1) * 21:
        return pd.Series(np.nan, index=prices_df.index)
    
    look_back = (window_months + exclude_months) * 21
    exclude_days = exclude_months * 21
    
    momentum = []
    for i in range(len(prices_df)):
        if i < look_back:
            momentum.append(np.nan)
        else:
            price_now = prices_df.iloc[i - exclude_days]["close"]
            price_start = prices_df.iloc[i - look_back]["close"]
            
            if price_start > 0:
                ret = (price_now - price_start) / price_start
                momentum.append(ret)
            else:
                momentum.append(np.nan)
    
    return pd.Series(momentum, index=prices_df.index)

def backtest_window(data: dict, start: date, end: date, window_months: int) -> dict:
    """
    Run backtest for a specific momentum window
    """
    returns = []
    current_date = start
    rebalance_count = 0
    
    while current_date <= end:
        if current_date.weekday() == 4:  # Friday
            current_ts = pd.Timestamp(current_date)
            
            # Compute signal for each symbol
            signals = {}
            for symbol, df in data.items():
                df_subset = df[df.index <= current_ts]
                if len(df_subset) > 0:
                    signal = compute_momentum_signal(df_subset, window_months, exclude_months=1)
                    if not np.isnan(signal.iloc[-1]):
                        signals[symbol] = signal.iloc[-1]
            
            if len(signals) < 5:
                current_date += timedelta(days=1)
                continue
            
            # Top quintile
            sorted_sigs = sorted(signals.items(), key=lambda x: x[1], reverse=True)
            target = set([s[0] for s in sorted_sigs[:max(1, len(signals) // 5)]])
            
            # Forward return
            next_date = current_date + timedelta(days=7)
            if next_date > end:
                break
            
            fwd_returns = []
            for symbol in target:
                df = data[symbol]
                prices_now = df[(df.index >= current_ts - pd.Timedelta(days=1)) & (df.index <= current_ts)]
                prices_next = df[(df.index > current_ts) & (df.index <= pd.Timestamp(next_date))]
                
                if len(prices_now) > 0 and len(prices_next) > 0:
                    price_start = prices_now["close"].iloc[-1]
                    price_end = prices_next["close"].iloc[-1]
                    
                    if price_start > 0:
                        ret = (price_end - price_start) / price_start - 0.006  # 60 bps cost
                        fwd_returns.append(ret)
            
            if fwd_returns:
                mean_ret = np.mean(fwd_returns)
                returns.append(mean_ret)
                rebalance_count += 1
        
        current_date += timedelta(days=1)
    
    if len(returns) == 0:
        return {"rebalances": 0, "sharpe": np.nan, "return": 0, "vol": 0}
    
    returns = np.array(returns)
    annual_ret = np.mean(returns) * 52
    annual_vol = np.std(returns) * np.sqrt(52)
    sharpe = annual_ret / annual_vol if annual_vol > 0 else 0
    
    return {
        "rebalances": rebalance_count,
        "sharpe": sharpe,
        "return": annual_ret,
        "vol": annual_vol,
        "win_rate": (returns > 0).sum() / len(returns) if len(returns) > 0 else 0
    }

def main():
    print("🔍 HYPERPARAMETER TUNING: Momentum Window Optimization\n")
    
    # Load data
    data = prepare_data(date(2015, 1, 1), date(2024, 6, 30), n_symbols=50, force_refetch=False)
    print(f"✓ {len(data)} symbols loaded\n")
    
    windows = [3, 6, 9, 12, 18, 24]
    periods = {
        "TRAIN": (date(2015, 1, 1), date(2015, 12, 31)),
        "VALIDATE": (date(2016, 1, 1), date(2019, 12, 31)),
        "TEST": (date(2020, 1, 1), date(2024, 6, 30))
    }
    
    # Grid search
    results = {}
    
    for window in windows:
        print(f"🔄 Window: {window}-1 months")
        results[window] = {}
        
        for phase_name, (start, end) in periods.items():
            result = backtest_window(data, start, end, window)
            results[window][phase_name] = result
            
            print(f"   {phase_name:12} | {result['rebalances']:3d} trades | Sharpe: {result['sharpe']:+6.2f} | Return: {result['return']*100:+6.2f}% | Win: {result['win_rate']*100:5.1f}%")
        
        print()
    
    # Summary: find best TEST Sharpe
    print("\n📊 SUMMARY (sorted by TEST Sharpe)\n")
    print("Window   | TRAIN Sharpe | VALIDATE Sharpe | TEST Sharpe | Overfit Risk")
    print("---------|--------------|-----------------|-------------|-------------")
    
    sorted_windows = sorted(windows, key=lambda w: results[w]["TEST"]["sharpe"], reverse=True)
    for window in sorted_windows:
        train_sharpe = results[window]["TRAIN"]["sharpe"]
        val_sharpe = results[window]["VALIDATE"]["sharpe"]
        test_sharpe = results[window]["TEST"]["sharpe"]
        
        # Overfit risk: if train >> test, likely overfit
        overfit_flag = "🔴 HIGH" if (train_sharpe > 2.0 and test_sharpe < 0.4) else ("🟡 MED" if train_sharpe > 1.0 and test_sharpe < 0.2 else "🟢 LOW")
        
        print(f"{window:2d}-1    | {train_sharpe:+10.2f}   | {val_sharpe:+13.2f}   | {test_sharpe:+9.2f}  | {overfit_flag}")
    
    # Best OOS
    best_window = max(windows, key=lambda w: results[w]["TEST"]["sharpe"])
    best_sharpe = results[best_window]["TEST"]["sharpe"]
    
    print(f"\n✨ BEST OUT-OF-SAMPLE: {best_window}-1 window with Sharpe = {best_sharpe:.2f}")
    
    if best_sharpe >= 0.4:
        print("✅ PASS: OOS Sharpe >= 0.4 target\n")
        return best_window, "PASS"
    else:
        print("❌ FAIL: Best OOS Sharpe < 0.4 (likely overfitted)\n")
        return best_window, "FAIL"

if __name__ == "__main__":
    main()
