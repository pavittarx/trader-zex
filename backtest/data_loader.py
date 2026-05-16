"""
data_loader.py — Convert Fyers OHLCV DataFrames to NautilusTrader Bar objects.

Timezone handling
-----------------
Fyers intraday bars have IST timezone-naive DatetimeIndex (i.e., the wall-clock
time in IST is stored as a naive timestamp). NautilusTrader requires all
timestamps in UTC nanoseconds.

Conversion: subtract 5h30m (19800 seconds) to shift IST → UTC, then read
pandas Timestamp.value which is already in nanoseconds.

For daily/weekly bars, Fyers returns date-only (no time component). We treat
the bar as opening at 09:15 IST, which converts to 03:45 UTC.
"""

from __future__ import annotations

import pandas as pd
from nautilus_trader.model.data import Bar, BarSpecification, BarType
from nautilus_trader.model.enums import AggregationSource, BarAggregation, PriceType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price, Quantity

_IST_OPEN_HOUR = 9
_IST_OPEN_MINUTE = 15
_IST_OFFSET = pd.Timedelta(hours=5, minutes=30)

# Fyers resolution → (step, BarAggregation)
_RESOLUTION_MAP: dict[str, tuple[int, BarAggregation]] = {
    "1":   (1,  BarAggregation.MINUTE),
    "5":   (5,  BarAggregation.MINUTE),
    "15":  (15, BarAggregation.MINUTE),
    "60":  (60, BarAggregation.MINUTE),
    "D":   (1,  BarAggregation.DAY),
    "W":   (1,  BarAggregation.WEEK),
    "M":   (1,  BarAggregation.MONTH),
}


def make_bar_type(instrument_id: InstrumentId, resolution: str) -> BarType:
    """Return the NautilusTrader BarType for a given Fyers resolution string."""
    step, agg = _RESOLUTION_MAP[resolution]
    spec = BarSpecification(step, agg, PriceType.LAST)
    return BarType(
        instrument_id=instrument_id,
        bar_spec=spec,
        aggregation_source=AggregationSource.EXTERNAL,
    )


def df_to_bars(df: pd.DataFrame, bar_type: BarType, resolution: str) -> list[Bar]:
    """
    Convert a Fyers OHLCV DataFrame to NautilusTrader Bar objects.

    Parameters
    ----------
    df         : DataFrame with columns open/high/low/close/volume and a
                 DatetimeIndex. Intraday: IST timezone-naive. EOD: date-only.
    bar_type   : the NautilusTrader BarType describing the bar series
    resolution : Fyers resolution string ("15", "60", "D", …)
    """
    bars: list[Bar] = []
    is_eod = resolution in ("D", "W", "M")

    for idx, row in df.iterrows():
        ts_ns = _to_utc_ns(idx, is_eod)

        bar = Bar(
            bar_type=bar_type,
            open=Price(round(float(row["open"]),   2), 2),
            high=Price(round(float(row["high"]),   2), 2),
            low=Price(round(float(row["low"]),    2), 2),
            close=Price(round(float(row["close"]), 2), 2),
            volume=Quantity(max(int(row["volume"]), 1), 0),
            ts_event=ts_ns,
            ts_init=ts_ns,
        )
        bars.append(bar)

    return bars


def _to_utc_ns(idx, is_eod: bool) -> int:
    """Convert a Fyers bar index (IST naive or date-only) to UTC nanoseconds."""
    if is_eod:
        # date-only index → set 09:15 IST open time
        ts_ist = pd.Timestamp(idx).replace(
            hour=_IST_OPEN_HOUR, minute=_IST_OPEN_MINUTE, second=0, microsecond=0
        )
    else:
        ts_ist = pd.Timestamp(idx)  # already IST wall-clock, timezone-naive

    ts_utc = ts_ist - _IST_OFFSET
    return int(ts_utc.value)
