"""
strategy.py — HMMConfluenceStrategy for NautilusTrader backtesting.

Entry rules (Long)
------------------
  60-min regime = Bullish  AND
  15-min signal ∈ {STRONG BUY, WEAK BUY}  AND
  no existing long position

Entry rules (Short)
-------------------
  60-min regime = Bearish  AND
  15-min signal ∈ {STRONG SELL, AVOID}  AND
  no existing short position

Exit rules
----------
  Long  : TAKE PROFIT signal | regime_60m → Bearish | stop-loss hit | EOD
  Short : location = At Support | regime_60m → Bullish | stop-loss hit | EOD

Position sizing
---------------
  Fixed fractional: risk BACKTEST_RISK_PCT of current equity per trade.
  Stop distance = |entry − stop_level|
  Shares = (equity × risk_pct) / stop_distance, rounded down to integer.

EOD exit
--------
  All positions flattened at BACKTEST_EOD_EXIT_HOUR_IST:BACKTEST_EOD_EXIT_MINUTE_IST
  (default 15:15 IST = 09:45 UTC). Applied every trading day.
"""

from __future__ import annotations

import logging
from zoneinfo import ZoneInfo

import pandas as pd
from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId, Venue
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy

import config

log = logging.getLogger(__name__)
_IST = ZoneInfo("Asia/Kolkata")


class HMMStrategyConfig(StrategyConfig, frozen=True):
    instrument_id: str
    bar_type_15m: str
    # Signal table: ISO timestamp string → signal dict
    # Stored as dict[str, dict] for JSON-serialisability (required by NT config)
    signal_records: dict  # {ts_iso: {regime_15m, regime_60m, signal_15m, ...}}
    risk_pct: float = config.BACKTEST_RISK_PCT
    stop_buffer: float = config.BACKTEST_STOP_BUFFER
    eod_exit_hour: int = config.BACKTEST_EOD_EXIT_HOUR_IST
    eod_exit_minute: int = config.BACKTEST_EOD_EXIT_MINUTE_IST


class HMMConfluenceStrategy(Strategy):
    """
    Trades based on pre-computed HMM regime + confluence signals.
    One instance per symbol; run inside a BacktestEngine.
    """

    def __init__(self, config: HMMStrategyConfig) -> None:
        super().__init__(config)
        self._iid = InstrumentId.from_str(config.instrument_id)
        self._bar_type = BarType.from_str(config.bar_type_15m)
        self._venue = Venue(config.instrument_id.split(".")[-1])

        # Build a pandas Series for fast timestamp lookup
        self._signals: pd.DataFrame = self._parse_signals(config.signal_records)

        self._position_side: str | None = None  # "LONG", "SHORT", or None
        self._stop_price: float | None = None
        self._entry_price: float | None = None
        self._trade_count = 0

    # ------------------------------------------------------------------
    # NautilusTrader lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.subscribe_bars(self._bar_type)

    def on_bar(self, bar: Bar) -> None:
        if bar.bar_type != self._bar_type:
            return

        close = float(bar.close)
        ts_ist = _bar_ts_to_ist(bar.ts_event)

        # EOD forced exit
        if self._position_side is not None:
            if _is_eod(ts_ist, self.config.eod_exit_hour, self.config.eod_exit_minute):
                self._close_position("EOD")
                return

        sig = self._get_signal(bar.ts_event)
        if sig is None:
            return

        regime_60 = sig.get("regime_60m", "Sideways")
        signal_15 = sig.get("signal_15m", "NEUTRAL")
        support = sig.get("support", 0.0)
        resistance = sig.get("resistance", 0.0)
        location = sig.get("location", "In Middle")

        # --- Exit existing position first ---
        if self._position_side == "LONG":
            stop_hit = self._stop_price and close <= self._stop_price
            if signal_15 == "TAKE PROFIT" or regime_60 == "Bearish" or stop_hit:
                self._close_position(f"LONG_EXIT ({signal_15})")
                return

        elif self._position_side == "SHORT":
            stop_hit = self._stop_price and close >= self._stop_price
            if location == "At Support" or regime_60 == "Bullish" or stop_hit:
                self._close_position(f"SHORT_EXIT ({signal_15})")
                return

        # --- Entry ---
        if self._position_side is None:
            if (
                regime_60 == "Bullish"
                and signal_15 in {"STRONG BUY", "WEAK BUY"}
            ):
                stop_level = support * (1 - self.config.stop_buffer)
                qty = self._position_size(close, stop_level)
                if qty > 0:
                    order = self.order_factory.market(
                        instrument_id=self._iid,
                        order_side=OrderSide.BUY,
                        quantity=Quantity.from_int(qty),
                        time_in_force=TimeInForce.GTC,
                    )
                    self.submit_order(order)
                    self._position_side = "LONG"
                    self._stop_price = stop_level
                    self._entry_price = close
                    self._trade_count += 1

            elif (
                regime_60 == "Bearish"
                and signal_15 in {"STRONG SELL", "AVOID"}
            ):
                stop_level = resistance * (1 + self.config.stop_buffer)
                qty = self._position_size(close, stop_level)
                if qty > 0:
                    order = self.order_factory.market(
                        instrument_id=self._iid,
                        order_side=OrderSide.SELL,
                        quantity=Quantity.from_int(qty),
                        time_in_force=TimeInForce.GTC,
                    )
                    self.submit_order(order)
                    self._position_side = "SHORT"
                    self._stop_price = stop_level
                    self._entry_price = close
                    self._trade_count += 1

    def on_stop(self) -> None:
        if self._position_side is not None:
            self.close_all_positions(self._iid)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _close_position(self, reason: str) -> None:
        self.log.info(f"Closing {self._position_side}: {reason}")
        self.close_all_positions(self._iid)
        self._position_side = None
        self._stop_price = None
        self._entry_price = None

    def _position_size(self, price: float, stop: float) -> int:
        """Shares to trade = (equity × risk_pct) / |price − stop|."""
        stop_distance = abs(price - stop)
        if stop_distance < 0.01:
            return 0
        try:
            equity = float(self.portfolio.equity(self._venue).as_decimal())
        except Exception:
            equity = config.BACKTEST_INITIAL_CAPITAL
        shares = int((equity * self.config.risk_pct) / stop_distance)
        return max(shares, 1)

    def _get_signal(self, ts_event_ns: int) -> dict | None:
        if self._signals.empty:
            return None
        ts = pd.Timestamp(ts_event_ns, unit="ns")
        # Convert from UTC back to IST for index lookup (signals indexed in IST)
        ts_ist = ts + pd.Timedelta(hours=5, minutes=30)
        # Try exact match first, then nearest prior bar
        try:
            return self._signals.loc[ts_ist].to_dict()
        except KeyError:
            # find nearest signal at or before this bar
            idx = self._signals.index.asof(ts_ist)
            if pd.isnull(idx):
                return None
            return self._signals.loc[idx].to_dict()

    @staticmethod
    def _parse_signals(records: dict) -> pd.DataFrame:
        if not records:
            return pd.DataFrame()
        df = pd.DataFrame.from_dict(records, orient="index")
        df.index = pd.to_datetime(df.index)
        df.sort_index(inplace=True)
        return df


def _bar_ts_to_ist(ts_event_ns: int) -> pd.Timestamp:
    ts_utc = pd.Timestamp(ts_event_ns, unit="ns")
    return ts_utc + pd.Timedelta(hours=5, minutes=30)


def _is_eod(ts_ist: pd.Timestamp, hour: int, minute: int) -> bool:
    return ts_ist.hour > hour or (ts_ist.hour == hour and ts_ist.minute >= minute)
