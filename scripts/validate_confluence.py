"""
scripts/validate_confluence.py

Empirically validates the confluence signal matrix by measuring forward
returns conditioned on each (regime, location) cell.

Usage
-----
    # Synthetic data (no credentials needed — approximate validation only):
    uv run python scripts/validate_confluence.py --synthetic

    # Real signals from signal_precompute output CSV:
    uv run python scripts/validate_confluence.py --signals path/to/signals.csv \
        --bars path/to/bars_15m.csv

Output
------
    A table showing, for each cell in the 3x3 confluence matrix:
    - Signal name
    - Number of occurrences
    - Mean forward 1-bar return (%)
    - Mean forward 4-bar return (%)
    - t-statistic (is it significantly different from zero?)
    - ✓ or ✗ whether the cell's direction matches its signal label

Interpretation
--------------
    Cells with |t| < 2 have no statistically significant edge.
    Cells where sign(mean_return) disagrees with signal direction are mislabeled.
    A STRONG BUY cell should have significantly higher forward return than NEUTRAL.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.confluence import generate_signal, _SIGNAL_TABLE
from core.hmm_model import HMMModel
from core.structure import StructureDetector
from core import config


# Expected direction for each signal (for validation)
_SIGNAL_DIRECTION: dict[str, int] = {
    "STRONG BUY":  +1,
    "WEAK BUY":    +1,
    "TAKE PROFIT": -1,   # expect reversal at resistance in bullish regime
    "WATCH":        0,
    "NEUTRAL":      0,
    "WAIT":         0,
    "AVOID":       -1,
    "STRONG SELL": -1,
}


def make_synthetic_bars(n: int = 1000) -> pd.DataFrame:
    """Synthetic OHLCV bars (15-min, NSE-like)."""
    rng = np.random.default_rng(42)
    # Add trending regimes to make the signals non-trivial
    third = n // 3
    trend = np.concatenate([
        rng.normal(0.0005, 0.005, third),          # bullish
        rng.normal(-0.0002, 0.008, third),         # bearish / volatile
        rng.normal(0.0001, 0.003, n - 2 * third),  # sideways (absorbs remainder)
    ])
    close = 100.0 * np.cumprod(1 + trend)
    m = len(close)  # actual number of bars (equals n)
    open_ = np.roll(close, 1); open_[0] = close[0]
    rng2 = np.random.default_rng(99)
    high = np.maximum(open_, close) * (1 + rng2.uniform(0, 0.004, m))
    low = np.minimum(open_, close) * (1 - rng2.uniform(0, 0.004, m))
    vol = rng2.integers(200_000, 3_000_000, m).astype(float)
    idx = pd.date_range("2024-01-02 09:15", periods=m, freq="15min")
    return pd.DataFrame({"open": open_, "high": high, "low": low,
                         "close": close, "volume": vol}, index=idx)


def compute_signals_from_bars(df: pd.DataFrame) -> pd.DataFrame:
    """Run rolling HMM + structure on df, return signals DataFrame."""
    hmm = HMMModel()
    det = StructureDetector()
    warmup = config.HMM_MIN_SAMPLES
    n = len(df)
    records = []

    for i in range(warmup, n):
        window = df.iloc[:i+1]
        try:
            hmm_result = hmm.detect_regime(window)
            struct = det.detect(window)
            signal = generate_signal(hmm_result.current_regime, struct.location)
            records.append({
                "timestamp": df.index[i],
                "regime": hmm_result.current_regime,
                "location": struct.location,
                "signal": signal,
                "close": float(df["close"].iloc[i]),
            })
        except Exception:
            continue

    return pd.DataFrame(records).set_index("timestamp") if records else pd.DataFrame()


def measure_forward_returns(
    signals_df: pd.DataFrame,
    bars_df: pd.DataFrame,
    horizons: tuple[int, ...] = (1, 4),
) -> pd.DataFrame:
    """
    For each signal bar, compute forward returns at each horizon.
    signals_df: indexed by timestamp with columns [regime, location, signal, close]
    bars_df:    full OHLCV bars (close column used)
    """
    rows = []
    close_series = bars_df["close"]

    for ts, row in signals_df.iterrows():
        try:
            pos = close_series.index.get_loc(ts)
        except KeyError:
            continue
        entry_price = float(row["close"])
        fwd = {}
        for h in horizons:
            if pos + h < len(close_series):
                fwd[f"fwd_{h}b"] = float(close_series.iloc[pos + h]) / entry_price - 1
            else:
                fwd[f"fwd_{h}b"] = float("nan")
        rows.append({
            "regime": row["regime"],
            "location": row["location"],
            "signal": row["signal"],
            **fwd,
        })

    return pd.DataFrame(rows)


def print_validation_report(df: pd.DataFrame, horizons: tuple[int, ...] = (1, 4)) -> None:
    """Print a validation table for each confluence cell."""
    all_regimes = ["Bullish", "Sideways", "Bearish"]
    all_locations = ["At Support", "In Middle", "At Resistance"]

    header = (f"{'Cell':<35} {'Signal':<14} {'N':>5} "
              + "".join(f"  {'fwd_'+str(h)+'b':>9}  {'t':>6}" for h in horizons)
              + "  OK?")
    print("\n" + "=" * len(header))
    print("CONFLUENCE MATRIX VALIDATION — Forward Return by Cell")
    print("=" * len(header))
    print(header)
    print("-" * len(header))

    for regime in all_regimes:
        for location in all_locations:
            signal = _SIGNAL_TABLE.get((regime, location), "NEUTRAL")
            cell = f"{regime} × {location}"
            subset = df[(df["regime"] == regime) & (df["location"] == location)]
            n = len(subset.dropna(subset=["fwd_1b"] if "fwd_1b" in subset.columns else []))

            fwd_parts = []
            ok = True
            for h in horizons:
                col = f"fwd_{h}b"
                if col not in subset.columns or subset[col].dropna().empty:
                    fwd_parts.append(f"  {'N/A':>9}  {'N/A':>6}")
                    continue
                vals = subset[col].dropna()
                mean_r = vals.mean()
                tstat, _ = stats.ttest_1samp(vals, 0.0)
                sig_ok = abs(tstat) >= 2.0

                # Check direction agreement
                expected_dir = _SIGNAL_DIRECTION.get(signal, 0)
                if expected_dir != 0 and sig_ok:
                    if (expected_dir > 0 and mean_r < 0) or (expected_dir < 0 and mean_r > 0):
                        ok = False

                fwd_parts.append(f"  {mean_r*100:+9.3f}%  {tstat:+6.2f}")

            ok_str = "✓" if ok else "✗ MISMATCH"
            print(f"{cell:<35} {signal:<14} {n:>5}{''.join(fwd_parts)}  {ok_str}")

    print("-" * len(header))
    print("\nInterpretation:")
    print("  |t| >= 2  → statistically significant forward return")
    print("  ✗ MISMATCH → signal direction disagrees with forward return (mislabeled cell)")
    print("  If most cells show |t| < 2, the matrix has no empirical edge.\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate confluence matrix empirically")
    parser.add_argument("--synthetic", action="store_true",
                        help="Use synthetic bar data (no credentials needed)")
    parser.add_argument("--signals", type=Path,
                        help="CSV of pre-computed signals (regime, location, signal, close columns)")
    parser.add_argument("--bars", type=Path,
                        help="CSV of OHLCV bars (needed with --signals for forward returns)")
    args = parser.parse_args()

    if args.signals and args.bars:
        print(f"Loading signals from {args.signals} ...")
        signals_df = pd.read_csv(args.signals, index_col=0, parse_dates=True)
        bars_df = pd.read_csv(args.bars, index_col=0, parse_dates=True)
    else:
        if not args.synthetic:
            print("No --signals/--bars provided; using synthetic data.")
        print("Generating 1000 bars of synthetic NSE-like 15-min data ...")
        bars_df = make_synthetic_bars(1000)
        print("Computing rolling signals (this may take ~30s) ...")
        signals_df = compute_signals_from_bars(bars_df)
        if signals_df.empty:
            print("No signals computed — check HMM_MIN_SAMPLES and data length.")
            sys.exit(1)

    print(f"Computing forward returns for {len(signals_df)} signal bars ...")
    fwd_df = measure_forward_returns(signals_df, bars_df)
    print_validation_report(fwd_df)


if __name__ == "__main__":
    main()
