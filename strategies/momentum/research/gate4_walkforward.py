"""
Gate 4: Walk-Forward Validation
Train 2005-2015 → Validate 2015-2020 → Test 2020+
Check if signal is real (OOS Sharpe > 0.3) or overfit
"""
import numpy as np
import pandas as pd
from datetime import date
from strategies.momentum.research.prepare_data import prepare_data
from strategies.momentum.signal import load_or_compute_signals, get_target_portfolio

def run_walkforward_test():
    """Split into train/validate/test, measure OOS signal strength"""
    
    print("🚶 WALK-FORWARD VALIDATION\n")
    
    # Load data once
    data = prepare_data(date(2015, 1, 1), date(2024, 6, 30), n_symbols=100, force_refetch=False)
    print(f"✓ {len(data)} symbols loaded\n")
    
    # Split periods
    periods = {
        "TRAIN": (date(2015, 1, 1), date(2015, 12, 31)),
        "VALIDATE": (date(2016, 1, 1), date(2019, 12, 31)),
        "TEST": (date(2020, 1, 1), date(2024, 6, 30))
    }
    
    for phase_name, (start, end) in periods.items():
        print(f"🔄 {phase_name} ({start} to {end}):")
        
        # Compute signals
        signals = load_or_compute_signals(data, start, end, force_recompute=True)
        
        # Simulate weekly rebalance
        returns = []
        from datetime import timedelta
        current_date = start
        rebalance_count = 0
        
        while current_date <= end:
            if current_date.weekday() == 4:  # Friday
                current_ts = pd.Timestamp(current_date)
                
                if current_ts not in signals.index:
                    current_date += timedelta(days=1)
                    continue
                
                # Get target portfolio
                target = get_target_portfolio(signals, current_ts, top_pct=0.20)
                if not target:
                    current_date += timedelta(days=1)
                    continue
                
                # Forward return
                next_date = current_date + timedelta(days=7)
                if next_date > end:
                    break
                
                fwd_returns = []
                for symbol in target:
                    if symbol not in data:
                        continue
                    
                    df = data[symbol]
                    prices_now = df[(df.index >= current_ts - pd.Timedelta(days=1)) & (df.index <= current_ts)]
                    prices_next = df[(df.index > current_ts) & (df.index <= pd.Timestamp(next_date))]
                    
                    if len(prices_now) > 0 and len(prices_next) > 0:
                        price_start = prices_now["close"].iloc[-1]
                        price_end = prices_next["close"].iloc[-1]
                        
                        if price_start > 0:
                            ret = (price_end - price_start) / price_start
                            ret -= 0.006  # 60 bps cost
                            fwd_returns.append(ret)
                
                if fwd_returns:
                    mean_ret = np.mean(fwd_returns)
                    returns.append(mean_ret)
                    rebalance_count += 1
            
            current_date += timedelta(days=1)
        
        if len(returns) == 0:
            print(f"   ❌ No rebalances (OOS signal failed)")
            continue
        
        returns = np.array(returns)
        annual_ret = np.mean(returns) * 52
        annual_vol = np.std(returns) * np.sqrt(52)
        sharpe = annual_ret / annual_vol if annual_vol > 0 else 0
        
        print(f"   Rebalances: {rebalance_count}")
        print(f"   Annual return: {annual_ret*100:+.2f}%")
        print(f"   Annual vol: {annual_vol*100:.2f}%")
        print(f"   Sharpe: {sharpe:.2f}")
        print(f"   Win rate: {(returns > 0).sum() / len(returns) * 100:.1f}%\n")

if __name__ == "__main__":
    run_walkforward_test()
