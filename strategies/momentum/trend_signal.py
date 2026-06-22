"""
Time-Series Momentum Signal: Trend-following component
- Rule: Score based on price position vs 200-day MA + 12-month momentum
- Reduces false positives from cross-sectional signal in bear regimes
"""
import numpy as np
import pandas as pd

def compute_trend_signal(prices_df: pd.DataFrame) -> pd.Series:
    """
    Compute time-series momentum signal: 0-100 percentile based on trend
    
    Rules:
    - 0-25: price < 200-day MA (bearish trend)
    - 25-50: price between 100-day and 200-day MA (mixed trend)
    - 50-75: price > 200-day MA but negative 12-month (weak uptrend)
    - 75-100: price > 200-day MA AND positive 12-month (strong uptrend)
    
    Returns signal 0-100 (0 = bearish, 100 = bullish)
    """
    if len(prices_df) < 250:
        return pd.Series(np.nan, index=prices_df.index)
    
    close = prices_df["close"].values
    signal = np.full(len(prices_df), np.nan)
    
    for i in range(250, len(prices_df)):
        # 200-day MA (trend indicator)
        ma200 = np.mean(close[i-200:i])
        ma100 = np.mean(close[i-100:i])
        current_price = close[i]
        
        # 12-month return (momentum)
        price_12m_ago = close[i - 252] if i >= 252 else close[0]
        ret_12m = (current_price - price_12m_ago) / price_12m_ago
        
        # Assign signal based on trend + momentum
        if current_price < ma200:
            # Bearish trend: below 200-day MA
            score = 10  # Very bearish
        elif current_price < ma100:
            # Mixed: between 100 and 200-day MA
            score = 40  # Neutral
        elif ret_12m < 0:
            # Weak uptrend: above MA but negative momentum
            score = 60  # Weak bullish
        else:
            # Strong uptrend: above MA and positive momentum
            score = 90  # Strong bullish
        
        signal[i] = score
    
    return pd.Series(signal, index=prices_df.index)

def combine_signals(cross_signal: pd.Series, ts_signal: pd.Series, cs_weight: float = 0.6) -> pd.Series:
    """
    Combine cross-sectional + time-series signals
    
    Parameters
    ----------
    cross_signal : pd.Series
        Cross-sectional momentum percentile (0-100)
    ts_signal : pd.Series
        Time-series momentum score (0-100)
    cs_weight : float
        Weight for cross-sectional signal (default 60/40 split)
    
    Returns
    -------
    pd.Series
        Combined signal (0-100)
    """
    combined = cross_signal * cs_weight + ts_signal * (1 - cs_weight)
    return combined
