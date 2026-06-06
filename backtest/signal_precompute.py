"""
signal_precompute.py — Rolling HMM + confluence signals with no look-ahead bias.

For each 15-min bar at index i, only bars[0..i] are used to compute the HMM
regime and structure levels. This mirrors what would be known in live trading
at that point in time.

Performance note
----------------
Computing a fresh HMM fit per bar is O(N²) total. For ~1,400 bars (90 days of
15-min data), this takes ~20-60 seconds per symbol. Results are cached to disk
keyed by (symbol, date_from, date_to) to avoid recomputation on reruns.

Output
------
DataFrame indexed by 15-min timestamp (UTC-naive, matching Fyers IST naive
timestamps converted consistently with data_loader.py) with columns:
  regime_15m, regime_60m, signal_15m, support, resistance, location,
  support_dist_pct, resistance_dist_pct
"""

from __future__ import annotations

import hashlib
import logging
import pickle
from pathlib import Path

import pandas as pd

from core import config
from core.confluence import generate_signal
from core.hmm_model import HMMModel
from core.structure import StructureDetector

log = logging.getLogger(__name__)

_CACHE_DIR = Path("~/.trader_zex_signal_cache").expanduser()
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Compute signal every bar (no interpolation — avoids stale signals at regime transitions)
_STEP = 1


def compute_rolling_signals(
    df_15m: pd.DataFrame,
    df_60m: pd.DataFrame,
    warmup: int = config.BACKTEST_SIGNAL_WARMUP,
    cache_key: str | None = None,
) -> pd.DataFrame:
    """
    Compute per-bar signals for df_15m using rolling windows of 15-min and
    60-min data. No future bar is ever accessed.

    Parameters
    ----------
    df_15m     : 15-min OHLCV DataFrame with DatetimeIndex (IST naive)
    df_60m     : 60-min OHLCV DataFrame with DatetimeIndex (IST naive)
    warmup     : minimum bars before signals start (default = HMM_MIN_SAMPLES)
    cache_key  : optional string key for disk cache; None = no caching

    Returns
    -------
    DataFrame indexed by 15-min timestamp with signal columns.
    """
    if cache_key:
        cached = _load_cache(cache_key)
        if cached is not None:
            log.info("Signal cache hit: %s (%d rows)", cache_key, len(cached))
            return cached

    log.info("Precomputing rolling signals (%d bars, step=%d) …", len(df_15m), _STEP)
    records = _compute(df_15m, df_60m, warmup)
    result = pd.DataFrame(records).set_index("timestamp") if records else pd.DataFrame()

    if cache_key and not result.empty:
        _save_cache(cache_key, result)

    return result


def _compute(
    df_15m: pd.DataFrame,
    df_60m: pd.DataFrame,
    warmup: int,
) -> list[dict]:
    # Separate HMM instances per timeframe: each carries its own warm-start
    # state across bars, so 15-min and 60-min fits never seed each other.
    hmm_15m = HMMModel(warm_start=True)
    hmm_60m = HMMModel(warm_start=True)
    det = StructureDetector()
    timestamps = df_15m.index.tolist()
    n = len(timestamps)
    records: list[dict] = []
    last_record: dict | None = None

    flip_count = 0
    prev_regime_15: str | None = None
    prev_regime_60: str | None = None

    for i in range(warmup, n):
        ts = timestamps[i]

        # Fill bars between computed steps by repeating the last known signal
        if i % _STEP != 0 and last_record is not None:
            records.append({**last_record, "timestamp": ts})
            continue

        window_15 = df_15m.iloc[: i + 1]
        window_60 = df_60m[df_60m.index <= ts]

        if len(window_60) < warmup // 4:
            continue

        try:
            hmm_15 = hmm_15m.detect_regime(window_15, max_window=config.HMM_MAX_WINDOW)
            struct = det.detect(window_15)
            signal = generate_signal(hmm_15.current_regime, struct.location)
            regime_15 = hmm_15.current_regime
        except Exception as exc:
            log.debug("15-min analysis failed at %s: %s", ts, exc)
            if last_record:
                records.append({**last_record, "timestamp": ts})
            continue

        try:
            hmm_60 = hmm_60m.detect_regime(window_60, max_window=config.HMM_MAX_WINDOW)
            regime_60 = hmm_60.current_regime
        except Exception:
            regime_60 = regime_15

        if prev_regime_15 is not None and regime_15 != prev_regime_15:
            flip_count += 1
        if prev_regime_60 is not None and regime_60 != prev_regime_60:
            flip_count += 1
        prev_regime_15 = regime_15
        prev_regime_60 = regime_60

        rec = {
            "timestamp": ts,
            "regime_15m": regime_15,
            "regime_60m": regime_60,
            "signal_15m": signal,
            "support": struct.support,
            "resistance": struct.resistance,
            "location": struct.location,
            "support_dist_pct": struct.support_dist_pct,
            "resistance_dist_pct": struct.resistance_dist_pct,
        }
        records.append(rec)
        last_record = rec

    total_bars = len(records)
    if total_bars > 0:
        log.info(
            "Regime label flips: %d across %d bars (%.1f%% flip rate) — "
            "high rate (>20%%) may indicate HMM label instability",
            flip_count, total_bars, 100 * flip_count / total_bars,
        )

    return records


def make_cache_key(symbol: str, date_from: object, date_to: object) -> str:
    """
    Generate a cache key that includes a hash of the relevant config params.
    This ensures stale signals are not reused when HMM or structure config changes.
    """
    cfg_str = (
        f"{config.HMM_N_STATES}_{config.HMM_RANDOM_STATE}_{config.HMM_MAX_WINDOW}_"
        f"{config.HMM_WARM_ITER}_"
        f"{config.STRUCTURE_METHOD}_{config.STRUCTURE_ATR_PERIOD}_"
        f"{config.STRUCTURE_EMA_PERIOD}_{config.STRUCTURE_ATR_MULT}_"
        f"{config.STRUCTURE_PROXIMITY_PCT}"
    )
    cfg_hash = hashlib.md5(cfg_str.encode()).hexdigest()[:8]
    raw = f"{symbol}_{date_from}_{date_to}_{cfg_hash}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def _cache_path(key: str) -> Path:
    return _CACHE_DIR / f"{key}.pkl"


def _load_cache(key: str) -> pd.DataFrame | None:
    path = _cache_path(key)
    if path.exists():
        try:
            with open(path, "rb") as f:
                return pickle.load(f)
        except Exception as exc:
            log.warning("Signal cache read failed (%s): %s", key, exc)
    return None


def _save_cache(key: str, df: pd.DataFrame) -> None:
    try:
        with open(_cache_path(key), "wb") as f:
            pickle.dump(df, f)
        log.debug("Signal cache saved: %s", key)
    except Exception as exc:
        log.warning("Signal cache write failed: %s", exc)
