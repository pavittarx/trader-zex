"""
scripts/check_label_stability.py

Measures HMM regime label stability across expanding windows.

Usage
-----
    # With a real OHLCV CSV (columns: datetime,open,high,low,close,volume):
    uv run python scripts/check_label_stability.py --csv path/to/data.csv

    # With synthetic data (for a quick sanity check without credentials):
    uv run python scripts/check_label_stability.py --synthetic

Output
------
    Prints a stability report:
    - What fraction of bars have their regime label changed when one more bar is added
    - A regime sequence plot (ASCII) showing where flips occur
    - Forward-return distribution per regime label
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.hmm_model import HMMModel
from core import config


def make_synthetic_data(n: int = 600) -> pd.DataFrame:
    """Generate a synthetic OHLCV dataframe for testing."""
    rng = np.random.default_rng(42)
    close = 100 * np.cumprod(1 + rng.normal(0.0002, 0.008, n))
    open_ = close * (1 + rng.normal(0, 0.002, n))
    high = np.maximum(close, open_) * (1 + rng.uniform(0, 0.005, n))
    low = np.minimum(close, open_) * (1 - rng.uniform(0, 0.005, n))
    volume = rng.integers(100_000, 2_000_000, n).astype(float)
    idx = pd.date_range("2024-01-01 09:15", periods=n, freq="15min")
    return pd.DataFrame({"open": open_, "high": high, "low": low,
                         "close": close, "volume": volume}, index=idx)


def check_stability(df: pd.DataFrame, warmup: int = config.HMM_MIN_SAMPLES) -> None:
    hmm = HMMModel()
    n = len(df)
    labels: list[str] = []

    print(f"\nChecking label stability on {n} bars (warmup={warmup}) ...")
    print("This fits the HMM on bars[0..i+1] for each i, then records the regime.")
    print("Then fits on bars[0..i+2] and checks if bar i's effective regime changed.\n")

    # Collect current_regime at each expanding window
    regimes_at_i: list[str] = []
    for i in range(warmup, n):
        window = df.iloc[:i+1]
        try:
            result = hmm.detect_regime(window)
            regimes_at_i.append(result.current_regime)
        except Exception:
            regimes_at_i.append("Error")

    # Count consecutive flips (bar i vs bar i-1)
    flips = sum(
        1 for a, b in zip(regimes_at_i[:-1], regimes_at_i[1:]) if a != b
    )
    total = len(regimes_at_i) - 1
    flip_rate = flips / total if total > 0 else 0.0

    print(f"Regime sequence (B=Bullish, S=Sideways, R=Bearish, E=Error):")
    abbrev = {"Bullish": "B", "Sideways": "S", "Bearish": "R", "Error": "E"}
    seq = "".join(abbrev.get(r, "?") for r in regimes_at_i)
    # Print in chunks of 80
    for start in range(0, len(seq), 80):
        print(f"  {seq[start:start+80]}")

    print(f"\nFlip rate: {flips}/{total} = {flip_rate:.1%}")
    if flip_rate > 0.20:
        print("  WARNING: HIGH -- labels are unstable. Consider HMM_MAX_WINDOW in config.py.")
    elif flip_rate > 0.10:
        print("  WARNING: MODERATE -- some instability. Monitor in live signals.")
    else:
        print("  OK: LOW -- labels appear stable.")

    # Forward return by regime
    print("\nForward 1-bar return by regime (mean +/- std):")
    close = df["close"].values
    for regime in ("Bullish", "Sideways", "Bearish"):
        indices = [
            warmup + i for i, r in enumerate(regimes_at_i)
            if r == regime and warmup + i + 1 < len(close)
        ]
        if not indices:
            print(f"  {regime:<10}: no samples")
            continue
        fwd = [(close[j+1] / close[j] - 1) for j in indices]
        arr = np.array(fwd)
        tstat = arr.mean() / (arr.std() / np.sqrt(len(arr))) if arr.std() > 0 else 0
        print(f"  {regime:<10}: n={len(arr):4d}  mean={arr.mean()*100:+.3f}%  "
              f"std={arr.std()*100:.3f}%  t={tstat:+.2f}")

    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="HMM label stability checker")
    parser.add_argument("--csv", type=Path, help="Path to OHLCV CSV file")
    parser.add_argument("--synthetic", action="store_true",
                        help="Use synthetic data instead of a CSV")
    args = parser.parse_args()

    if args.synthetic or args.csv is None:
        print("Using synthetic data (600 bars of simulated 15-min NSE-like returns)")
        df = make_synthetic_data(600)
    else:
        df = pd.read_csv(args.csv, index_col=0, parse_dates=True)
        required = {"open", "high", "low", "close", "volume"}
        if not required.issubset(df.columns):
            print(f"CSV must have columns: {required}")
            sys.exit(1)

    check_stability(df)


if __name__ == "__main__":
    main()
