"""
StructureDetector — identifies support and resistance levels from OHLCV data.

Two methods (controlled by config.STRUCTURE_METHOD):

  atr (default) — Keltner-style ATR bands
    support    = EMA(close, N) − multiplier × ATR(N)
    resistance = EMA(close, N) + multiplier × ATR(N)
    Robust on all timeframes; no look-ahead bias.

  pivot — scipy swing high/low detection
    Finds the nearest swing low below price (support) and
    nearest swing high above price (resistance).
    More intuitive but noisier on short timeframes.

Returns a StructureResult with support, resistance, location label,
and percentage distances from the current price to each level.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

import config


@dataclass
class StructureResult:
    support: float
    resistance: float
    location: str               # "At Support" | "At Resistance" | "In Middle"
    support_dist_pct: float     # how far price is above support (%)
    resistance_dist_pct: float  # how far price is below resistance (%)


class StructureDetector:
    def __init__(
        self,
        method: str = config.STRUCTURE_METHOD,
        atr_period: int = config.STRUCTURE_ATR_PERIOD,
        ema_period: int = config.STRUCTURE_EMA_PERIOD,
        atr_multiplier: float = config.STRUCTURE_ATR_MULT,
        proximity_pct: float = config.STRUCTURE_PROXIMITY_PCT,
        pivot_distance: int = config.STRUCTURE_PIVOT_DISTANCE,
    ) -> None:
        self.method = method
        self.atr_period = atr_period
        self.ema_period = ema_period
        self.atr_multiplier = atr_multiplier
        self.proximity_pct = proximity_pct
        self.pivot_distance = pivot_distance

    def detect(self, data: pd.DataFrame) -> StructureResult:
        if self.method == "pivot":
            return self._detect_pivot(data)
        return self._detect_atr(data)

    # ------------------------------------------------------------------
    # ATR bands
    # ------------------------------------------------------------------

    def _detect_atr(self, data: pd.DataFrame) -> StructureResult:
        close = data["close"]
        high  = data["high"]
        low   = data["low"]

        prev_close = close.shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low  - prev_close).abs(),
        ], axis=1).max(axis=1)

        atr = tr.ewm(span=self.atr_period, adjust=False).mean()
        ema = close.ewm(span=self.ema_period, adjust=False).mean()

        support    = (ema - self.atr_multiplier * atr).iloc[-1]
        resistance = (ema + self.atr_multiplier * atr).iloc[-1]
        price      = close.iloc[-1]

        return self._build_result(price, support, resistance)

    # ------------------------------------------------------------------
    # Pivot point peaks
    # ------------------------------------------------------------------

    def _detect_pivot(self, data: pd.DataFrame) -> StructureResult:
        highs = data["high"].values
        lows  = data["low"].values
        price = data["close"].iloc[-1]

        peak_idx,   _ = find_peaks( highs, distance=self.pivot_distance)
        trough_idx, _ = find_peaks(-lows,  distance=self.pivot_distance)

        swing_lows  = lows[trough_idx]
        swing_highs = highs[peak_idx]

        below = swing_lows[swing_lows < price]
        above = swing_highs[swing_highs > price]

        support    = float(below.max()) if len(below) > 0 else float(lows.min())
        resistance = float(above.min()) if len(above) > 0 else float(price * 1.02)

        return self._build_result(price, support, resistance)

    # ------------------------------------------------------------------
    # Shared result builder
    # ------------------------------------------------------------------

    def _build_result(self, price: float, support: float, resistance: float) -> StructureResult:
        if price == 0:
            return StructureResult(support=0.0, resistance=0.0, location="In Middle",
                                   support_dist_pct=0.0, resistance_dist_pct=0.0)
        support_dist    = (price - support)    / price * 100
        resistance_dist = (resistance - price) / price * 100

        if support_dist <= self.proximity_pct:
            location = "At Support"
        elif resistance_dist <= self.proximity_pct:
            location = "At Resistance"
        else:
            location = "In Middle"

        return StructureResult(
            support=round(support, 2),
            resistance=round(resistance, 2),
            location=location,
            support_dist_pct=round(support_dist, 2),
            resistance_dist_pct=round(resistance_dist, 2),
        )
