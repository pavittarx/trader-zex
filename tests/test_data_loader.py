"""
test_data_loader.py — Tests for backtest/data_loader.py.

Covers:
  - IST → UTC nanosecond conversion (_to_utc_ns)
  - EOD bars (date-only index → 09:15 IST = 03:45 UTC)
  - OHLC consistency in df_to_bars output (high >= open/close >= low)
"""
import pandas as pd
import pytest

nautilus_trader = pytest.importorskip("nautilus_trader")

from core.backtest.data_loader import _to_utc_ns, df_to_bars, make_bar_type
from core.backtest.instruments import fyers_to_instrument_id


# ---------------------------------------------------------------------------
# _to_utc_ns — IST → UTC conversion
# ---------------------------------------------------------------------------


class TestToUtcNs:
    def test_intraday_09h15_ist_equals_03h45_utc(self):
        """09:15 IST should become 03:45 UTC (subtract 5h30m)."""
        ts_ist = pd.Timestamp("2024-01-02 09:15:00")
        ns = _to_utc_ns(ts_ist, is_eod=False)
        ts_utc = pd.Timestamp(ns)
        assert ts_utc == pd.Timestamp("2024-01-02 03:45:00")

    def test_intraday_returns_integer_nanoseconds(self):
        """Return value must be a Python int (nanoseconds since epoch)."""
        ts_ist = pd.Timestamp("2024-01-02 09:15:00")
        ns = _to_utc_ns(ts_ist, is_eod=False)
        assert isinstance(ns, int)

    def test_intraday_known_timestamp_value(self):
        """Cross-check the nanosecond value against manual calculation."""
        ts_ist = pd.Timestamp("2024-01-02 09:15:00")
        expected_utc = pd.Timestamp("2024-01-02 03:45:00")
        ns = _to_utc_ns(ts_ist, is_eod=False)
        assert ns == expected_utc.value

    def test_eod_date_only_maps_to_09h15_ist(self):
        """A date-only EOD index entry should become 09:15 IST = 03:45 UTC."""
        ts_date = pd.Timestamp("2024-01-02")
        ns = _to_utc_ns(ts_date, is_eod=True)
        ts_utc = pd.Timestamp(ns)
        assert ts_utc == pd.Timestamp("2024-01-02 03:45:00")

    def test_eod_and_intraday_same_result_for_same_day(self):
        """EOD bar for a date and intraday 09:15 bar produce the same UTC ns."""
        ts_date = pd.Timestamp("2024-03-15")
        ts_intra = pd.Timestamp("2024-03-15 09:15:00")
        assert _to_utc_ns(ts_date, is_eod=True) == _to_utc_ns(ts_intra, is_eod=False)

    def test_ist_offset_exactly_5h30m(self):
        """Verify the IST−UTC offset is exactly 5 hours 30 minutes."""
        ts_ist = pd.Timestamp("2024-06-01 15:30:00")
        ns = _to_utc_ns(ts_ist, is_eod=False)
        ts_utc = pd.Timestamp(ns)
        delta = ts_ist - ts_utc
        assert delta == pd.Timedelta(hours=5, minutes=30)


# ---------------------------------------------------------------------------
# df_to_bars — OHLC consistency
# ---------------------------------------------------------------------------


class TestDfToBars:
    @pytest.fixture
    def bar_type(self):
        iid = fyers_to_instrument_id("NSE:RELIANCE-EQ")
        return make_bar_type(iid, "15")

    @pytest.fixture
    def basic_df(self):
        """Five bars with tidy OHLC values."""
        dates = pd.date_range("2024-01-02 09:15", periods=5, freq="15min")
        close = [100.0, 101.0, 102.0, 101.5, 103.0]
        high  = [c + 1.0 for c in close]
        low   = [c - 1.0 for c in close]
        open_ = close[:]  # open == close (simple case)
        return pd.DataFrame(
            {"open": open_, "high": high, "low": low, "close": close, "volume": [10_000] * 5},
            index=dates,
        )

    def test_returns_correct_number_of_bars(self, basic_df, bar_type):
        bars = df_to_bars(basic_df, bar_type, "15")
        assert len(bars) == 5

    def test_high_ge_close(self, basic_df, bar_type):
        bars = df_to_bars(basic_df, bar_type, "15")
        for bar in bars:
            assert float(bar.high) >= float(bar.close), f"high < close: {bar}"

    def test_close_ge_low(self, basic_df, bar_type):
        bars = df_to_bars(basic_df, bar_type, "15")
        for bar in bars:
            assert float(bar.close) >= float(bar.low), f"close < low: {bar}"

    def test_high_ge_open(self, basic_df, bar_type):
        bars = df_to_bars(basic_df, bar_type, "15")
        for bar in bars:
            assert float(bar.high) >= float(bar.open), f"high < open: {bar}"

    def test_open_ge_low(self, basic_df, bar_type):
        bars = df_to_bars(basic_df, bar_type, "15")
        for bar in bars:
            assert float(bar.open) >= float(bar.low), f"open < low: {bar}"

    def test_ts_event_is_utc_nanoseconds(self, basic_df, bar_type):
        """ts_event should be UTC nanoseconds for the 09:15 IST bar = 03:45 UTC."""
        bars = df_to_bars(basic_df, bar_type, "15")
        first_bar = bars[0]
        expected_utc = pd.Timestamp("2024-01-02 03:45:00")
        assert first_bar.ts_event == expected_utc.value

    def test_volume_at_least_one(self, bar_type):
        """Zero-volume bars should be coerced to volume=1 (avoids NT rejection)."""
        dates = pd.date_range("2024-01-02 09:15", periods=2, freq="15min")
        df = pd.DataFrame(
            {"open": [100.0, 100.0], "high": [101.0, 101.0],
             "low": [99.0, 99.0], "close": [100.0, 100.0], "volume": [0, 0]},
            index=dates,
        )
        bars = df_to_bars(df, bar_type, "15")
        for bar in bars:
            assert int(bar.volume) >= 1

    def test_eod_bar_ts_event_correct(self, bar_type):
        """EOD (daily) bar with date-only index should map to 09:15 IST = 03:45 UTC."""
        iid = fyers_to_instrument_id("NSE:RELIANCE-EQ")
        day_bar_type = make_bar_type(iid, "D")
        dates = pd.to_datetime(["2024-01-02", "2024-01-03"])
        df = pd.DataFrame(
            {"open": [100.0, 101.0], "high": [102.0, 103.0],
             "low": [99.0, 100.0], "close": [101.0, 102.0], "volume": [100_000, 110_000]},
            index=dates,
        )
        bars = df_to_bars(df, day_bar_type, "D")
        expected_utc = pd.Timestamp("2024-01-02 03:45:00")
        assert bars[0].ts_event == expected_utc.value
