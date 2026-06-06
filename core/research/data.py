"""Chunked history fetching with an on-disk parquet cache.

Fyers caps a single request (~366 days for 1D, ~100 days intraday), so both
fetchers walk the range in chunks and stitch. The cache key includes the
venue so a second broker never collides with NSE data.
"""
from __future__ import annotations

import hashlib
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from core import config

CACHE_VERSION = 1  # bump to invalidate all cached frames
_CACHE_DIR = Path("~/.trader_zex_research_cache").expanduser()


def _cache_path(venue: str, sym: str, resolution: str, frm: date, to: date) -> Path:
    raw = f"v{CACHE_VERSION}_{venue}_{sym}_{resolution}_{frm}_{to}"
    return _CACHE_DIR / f"{hashlib.md5(raw.encode()).hexdigest()[:20]}.parquet"


def _fetch_chunked(client, sym: str, resolution: str, frm: date, to: date,
                   chunk_days: int, sleep_sec: float = 0.0) -> pd.DataFrame:
    parts, cur = [], frm
    while cur <= to:
        end = min(cur + timedelta(days=chunk_days - 1), to)
        try:
            df = client.get_history(sym, resolution, date_from=cur, date_to=end)
            if not df.empty:
                parts.append(df)
        except Exception:
            pass
        cur = end + timedelta(days=1)
        if sleep_sec:
            time.sleep(sleep_sec)
    if not parts:
        return pd.DataFrame()
    allp = pd.concat(parts).sort_index()
    return allp[~allp.index.duplicated()]


def fetch_daily(client, sym: str, frm: date, to: date, *,
                chunk_days: int = 360, venue: str = "NSE",
                use_cache: bool = True) -> pd.DataFrame:
    """Daily history in <=chunk_days windows (Fyers caps 1D at 366 days/request)."""
    cp = _cache_path(venue, sym, "D", frm, to)
    if use_cache and cp.exists():
        return pd.read_parquet(cp)
    df = _fetch_chunked(client, sym, "D", frm, to, chunk_days)
    if use_cache and not df.empty:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cp)
    return df


def fetch_intraday(client, sym: str, frm: date, to: date, *,
                   resolution: str = "15", chunk_days: int = 95,
                   venue: str = "NSE", use_cache: bool = True) -> pd.DataFrame:
    """Intraday history in <=chunk_days windows, rate-limit sleep between calls."""
    cp = _cache_path(venue, sym, resolution, frm, to)
    if use_cache and cp.exists():
        return pd.read_parquet(cp)
    df = _fetch_chunked(client, sym, resolution, frm, to, chunk_days,
                        sleep_sec=config.API_SLEEP_SECONDS)
    if use_cache and not df.empty:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cp)
    return df
