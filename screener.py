"""
Screener — runs the HMM regime detector across multiple symbols and timeframes.

API call strategy
-----------------
Instead of one call per (symbol × timeframe), we batch per symbol:
  - One 1-min fetch  → resample to every requested intraday timeframe  (5, 15, 60 …)
  - One daily fetch  → used directly for D/W/M timeframes

For N symbols and T timeframes (mix of intraday + EOD) this reduces calls from
N×T  to  N×2 (or N×1 when only intraday or only EOD is requested).
"""

import logging
import time

import pandas as pd

import config
from fyers_client import (
    EOD_RESOLUTIONS,
    INTRADAY_RESOLUTIONS,
    RESAMPLE_RULES,
    FyersClient,
    resample_ohlcv,
)
from hmm_model import HMMModel

log = logging.getLogger(__name__)

_REGIME_ICONS = {
    "Bullish":  "▲ Bullish",
    "Sideways": "— Sideways",
    "Bearish":  "▼ Bearish",
    "Error":    "✕ Error",
}


class Screener:
    """
    Multi-symbol, multi-timeframe regime screener.

    Usage
    -----
    >>> client = FyersClient()
    >>> table = Screener(client).run()
    >>> print(table)
    """

    def __init__(self, client: FyersClient) -> None:
        self._client = client

    def run(
        self,
        symbols: list[str] = config.DEFAULT_SYMBOLS,
        timeframes: list[str] = config.DEFAULT_TIMEFRAMES,
        *,
        sleep_sec: float = config.API_SLEEP_SECONDS,
        show_icons: bool = True,
    ) -> pd.DataFrame:
        """
        Screen *symbols* across *timeframes* and return a regime summary table.

        Returns
        -------
        pd.DataFrame  — index=symbol, columns=[Price, Chg%, *timeframes]
        """
        intraday_tfs = [tf for tf in timeframes if tf in INTRADAY_RESOLUTIONS]
        eod_tfs      = [tf for tf in timeframes if tf in EOD_RESOLUTIONS]

        rows: dict[str, dict[str, str]] = {sym: {} for sym in symbols}
        total = len(symbols)

        for i, sym in enumerate(symbols, 1):
            log.info("[%d/%d]  %s", i, total, sym)
            rows[sym] = self._detect_all_timeframes(sym, intraday_tfs, eod_tfs, sleep_sec)

        df = pd.DataFrame(rows).T
        df.index.name = "Symbol"
        df.columns.name = "Timeframe"
        df = df[timeframes]

        if show_icons:
            df = df.map(lambda v: _REGIME_ICONS.get(v, v))

        quotes = self._fetch_quotes(symbols)
        df.insert(0, "Chg%",  quotes["change_pct"].map(self._fmt_change))
        df.insert(0, "Price", quotes["ltp"].map(self._fmt_price))

        return df

    # ------------------------------------------------------------------
    # Per-symbol batching
    # ------------------------------------------------------------------

    def _detect_all_timeframes(
        self,
        symbol: str,
        intraday_tfs: list[str],
        eod_tfs: list[str],
        sleep_sec: float,
    ) -> dict[str, str]:
        results: dict[str, str] = {}

        # --- One 1-min fetch → resample to all intraday timeframes ---
        if intraday_tfs:
            try:
                base = self._client.get_history(symbol, "1")
                if base.empty:
                    raise ValueError("empty response")
                log.debug("  Fetched %d 1-min bars for %s", len(base), symbol)
                for tf in intraday_tfs:
                    rule = RESAMPLE_RULES[tf]
                    resampled = resample_ohlcv(base, rule)
                    log.debug("  %s @ %s → %d bars (resampled)", symbol, tf, len(resampled))
                    results[tf] = self._run_hmm(resampled, symbol, tf)
            except Exception as exc:
                log.error("%s intraday fetch failed: %s", symbol, exc)
                for tf in intraday_tfs:
                    results[tf] = "Error"
            time.sleep(sleep_sec)

        # --- One fetch per EOD timeframe (different lookback periods) ---
        for tf in eod_tfs:
            try:
                data = self._client.get_history(symbol, tf)
                if data.empty:
                    raise ValueError("empty response")
                results[tf] = self._run_hmm(data, symbol, tf)
            except Exception as exc:
                log.error("%s @ %s failed: %s", symbol, tf, exc)
                results[tf] = "Error"
            time.sleep(sleep_sec)

        return results

    def _run_hmm(self, data: pd.DataFrame, symbol: str, tf: str) -> str:
        try:
            result = HMMModel().detect_regime(data)
            if not result.converged:
                log.warning("%s @ %s: HMM did not converge", symbol, tf)
            return result.current_regime
        except Exception as exc:
            log.error("%s @ %s HMM failed: %s", symbol, tf, exc)
            return "Error"

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _fmt_price(val) -> str:
        return f"₹{val:,.2f}" if pd.notna(val) else "—"

    @staticmethod
    def _fmt_change(val) -> str:
        if pd.isna(val):
            return "—"
        arrow = "▲" if val >= 0 else "▼"
        return f"{arrow} {abs(val):.2f}%"

    def _fetch_quotes(self, symbols: list[str]) -> pd.DataFrame:
        try:
            return self._client.get_quotes(symbols)
        except Exception as exc:
            log.warning("Could not fetch quotes: %s", exc)
            return pd.DataFrame(index=symbols, columns=["ltp", "change_pct"])
