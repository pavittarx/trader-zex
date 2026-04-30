"""
Screener — runs HMM regime detection + structural analysis across
multiple symbols and timeframes, then produces a confluence signal table.

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
from collections.abc import Generator
from dataclasses import dataclass

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
from confluence import generate_signal, format_signal
from structure import StructureDetector, StructureResult

log = logging.getLogger(__name__)

_REGIME_ICONS = {
    "Bullish": "▲ Bullish",
    "Sideways": "— Sideways",
    "Bearish": "▼ Bearish",
    "Error": "✕ Error",
}


@dataclass
class BarAnalysis:
    regime: str
    signal: str
    support: float
    resistance: float
    support_dist_pct: float
    resistance_dist_pct: float
    location: str


class Screener:
    """
    Multi-symbol, multi-timeframe regime + confluence screener.

    Usage
    -----
    >>> client = FyersClient()
    >>> regimes, signals, levels = Screener(client).run()
    >>> print(regimes)
    >>> print(signals)
    """

    def __init__(self, client: FyersClient) -> None:
        self._client = client
        self._structure = StructureDetector()

    def run(
        self,
        symbols: list[str] = config.DEFAULT_SYMBOLS,
        timeframes: list[str] = config.DEFAULT_TIMEFRAMES,
        *,
        sleep_sec: float = config.API_SLEEP_SECONDS,
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        Screen *symbols* across *timeframes*.

        Returns
        -------
        regimes : DataFrame — index=symbol, columns=[Price, Chg%, *timeframes], regime labels
        signals : DataFrame — index=symbol, columns=timeframes, confluence signal labels
        levels  : DataFrame — index=symbol, columns=[Support, Resistance, Dist_S%, Dist_R%]
                  (uses the last timeframe as reference for levels)
        """
        intraday_tfs, eod_tfs = self._partition_timeframes(timeframes)
        raw: dict[str, dict[str, BarAnalysis]] = {}
        total = len(symbols)

        for i, sym in enumerate(symbols, 1):
            log.info("[%d/%d]  %s", i, total, sym)
            raw[sym] = self._analyse_all_timeframes(sym, intraday_tfs, eod_tfs, sleep_sec)

        quotes = self._fetch_quotes(symbols)
        return self._build_dataframes(raw, quotes, timeframes)

    def stream(
        self,
        symbols: list[str] = config.DEFAULT_SYMBOLS,
        timeframes: list[str] = config.DEFAULT_TIMEFRAMES,
        *,
        sleep_sec: float = config.API_SLEEP_SECONDS,
    ) -> Generator[tuple[int, int, pd.DataFrame, pd.DataFrame, pd.DataFrame], None, None]:
        """
        Like run(), but yields (i, total, regimes, signals, levels) after each
        symbol so the caller can display partial results progressively.
        """
        intraday_tfs, eod_tfs = self._partition_timeframes(timeframes)
        quotes = self._fetch_quotes(symbols)
        raw: dict[str, dict[str, BarAnalysis]] = {}
        total = len(symbols)

        for i, sym in enumerate(symbols, 1):
            log.info("[%d/%d]  %s", i, total, sym)
            raw[sym] = self._analyse_all_timeframes(sym, intraday_tfs, eod_tfs, sleep_sec)
            yield i, total, *self._build_dataframes(raw, quotes, timeframes)

    # ------------------------------------------------------------------
    # DataFrame builder (shared by run and stream)
    # ------------------------------------------------------------------

    @staticmethod
    def _partition_timeframes(timeframes: list[str]) -> tuple[list[str], list[str]]:
        return (
            [tf for tf in timeframes if tf in INTRADAY_RESOLUTIONS],
            [tf for tf in timeframes if tf in EOD_RESOLUTIONS],
        )

    def _build_dataframes(
        self,
        raw: dict[str, dict[str, BarAnalysis]],
        quotes: pd.DataFrame,
        timeframes: list[str],
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        symbols = list(raw.keys())
        q = quotes.reindex(symbols)  # reindex once, reuse for both Price and Chg%

        regime_data = {
            sym: {tf: _REGIME_ICONS.get(a.regime, a.regime) for tf, a in tfs.items()}
            for sym, tfs in raw.items()
        }
        regimes = pd.DataFrame(regime_data).T.reindex(columns=timeframes)
        regimes.index.name = "Symbol"
        regimes.insert(0, "Chg%", q["change_pct"].map(self._fmt_change))
        regimes.insert(0, "Price", q["ltp"].map(self._fmt_price))

        signal_data = {
            sym: {tf: format_signal(a.signal) for tf, a in tfs.items()}
            for sym, tfs in raw.items()
        }
        signals = pd.DataFrame(signal_data).T.reindex(columns=timeframes)
        signals.index.name = "Symbol"

        ref_tf = timeframes[-1]
        level_rows = []
        for sym, tfs in raw.items():
            a = tfs.get(ref_tf)
            if a and a.regime != "Error":
                level_rows.append({
                    "Symbol": sym,
                    "Support": self._fmt_price(a.support),
                    "Dist_S%": f"{a.support_dist_pct:.1f}%",
                    "Resistance": self._fmt_price(a.resistance),
                    "Dist_R%": f"{a.resistance_dist_pct:.1f}%",
                    "Location": a.location,
                })
            else:
                level_rows.append({
                    "Symbol": sym,
                    "Support": "—", "Dist_S%": "—",
                    "Resistance": "—", "Dist_R%": "—", "Location": "—",
                })
        levels = pd.DataFrame(level_rows).set_index("Symbol")

        return regimes, signals, levels

    # ------------------------------------------------------------------
    # Per-symbol batching
    # ------------------------------------------------------------------

    def _analyse_all_timeframes(
        self,
        symbol: str,
        intraday_tfs: list[str],
        eod_tfs: list[str],
        sleep_sec: float,
    ) -> dict[str, BarAnalysis]:
        results: dict[str, BarAnalysis] = {}

        if intraday_tfs:
            try:
                base = self._client.get_history(symbol, "1")
                if base.empty:
                    raise ValueError("empty response")
                log.debug("  Fetched %d 1-min bars for %s", len(base), symbol)
                for tf in intraday_tfs:
                    resampled = resample_ohlcv(base, RESAMPLE_RULES[tf])
                    log.debug("  %s @ %s → %d bars", symbol, tf, len(resampled))
                    results[tf] = self._analyse(resampled, symbol, tf)
            except Exception as exc:
                log.error("%s intraday fetch failed: %s", symbol, exc)
                for tf in intraday_tfs:
                    results[tf] = self._error_analysis()
            time.sleep(sleep_sec)

        for tf in eod_tfs:
            try:
                data = self._client.get_history(symbol, tf)
                if data.empty:
                    raise ValueError("empty response")
                results[tf] = self._analyse(data, symbol, tf)
            except Exception as exc:
                log.error("%s @ %s failed: %s", symbol, tf, exc)
                results[tf] = self._error_analysis()
            time.sleep(sleep_sec)

        return results

    def _analyse(self, data: pd.DataFrame, symbol: str, tf: str) -> BarAnalysis:
        try:
            hmm_result = HMMModel().detect_regime(data)
            if not hmm_result.converged:
                log.warning("%s @ %s: HMM did not converge", symbol, tf)

            struct: StructureResult = self._structure.detect(data)
            sig = generate_signal(hmm_result.current_regime, struct.location)

            return BarAnalysis(
                regime=hmm_result.current_regime,
                signal=sig,
                support=struct.support,
                resistance=struct.resistance,
                support_dist_pct=struct.support_dist_pct,
                resistance_dist_pct=struct.resistance_dist_pct,
                location=struct.location,
            )
        except Exception as exc:
            log.error("%s @ %s analysis failed: %s", symbol, tf, exc)
            return self._error_analysis()

    @staticmethod
    def _error_analysis() -> BarAnalysis:
        return BarAnalysis(
            regime="Error",
            signal="NEUTRAL",
            support=0.0,
            resistance=0.0,
            support_dist_pct=0.0,
            resistance_dist_pct=0.0,
            location="—",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _fmt_price(val) -> str:
        return f"₹{val:,.2f}" if pd.notna(val) and val else "—"

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
