"""
conftest.py — Shared fixtures for trader-zex tests.
"""
import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def sample_ohlcv_df():
    """
    Return a DataFrame with valid OHLC + volume columns and IST-naive DatetimeIndex.

    Suitable for passing to HMMModel.detect_regime() and backtest data_loader.
    Uses n=210 bars (> HMM_MIN_SAMPLES=100) so the HMM can always fit.
    """
    n = 210
    rng = np.random.default_rng(42)
    dates = pd.date_range("2024-01-02 09:15", periods=n, freq="15min")

    # Geometric random walk so close is always positive
    log_returns = rng.normal(0.0002, 0.005, n)
    close = 100.0 * np.exp(np.cumsum(log_returns))

    # High >= close >= low
    half_range = np.abs(rng.normal(0, 0.3, n)) + 0.05
    high = close + half_range
    low = close - half_range
    open_ = close + rng.normal(0, 0.2, n)
    open_ = np.clip(open_, low, high)  # keep open inside [low, high]

    volume = rng.integers(5_000, 50_000, n).astype(float)

    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )


@pytest.fixture
def sample_positions_df():
    """
    Return a DataFrame mimicking NautilusTrader's positions report.

    The realized_pnl column uses the "NNN.NN INR" string format that
    NautilusTrader emits and metrics._from_positions() must parse.
    """
    return pd.DataFrame(
        {
            "instrument_id": ["RELIANCE-EQ.NSE", "TCS-EQ.NSE", "INFY-EQ.NSE"],
            "realized_pnl": ["2910.00 INR", "-500.00 INR", "0.00 INR"],
            "commissions": ["[650.00 INR]", "[120.00 INR]", "[45.00 INR]"],
        }
    )
