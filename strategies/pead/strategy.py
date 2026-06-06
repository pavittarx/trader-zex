"""pead_strategy.py — PEAD as a NautilusTrader Strategy (backtest AND live).

One instance per symbol. Daily bars. The SAME class runs in the BacktestEngine
and (later) a live/sandbox TradingNode, so backtest and live share one codepath.

Rules (PEAD_PLAYBOOK.md) + risk guards:
  ENTRY  : flat, today is this symbol's earnings reaction day, reaction >= +2%
           (long-only — shorts need F&O). Size = alloc_pct of equity, capped by
           a portfolio gross-exposure limit.
  EXITS  : (1) STOP        — close <= entry*(1-stop_pct)        [disaster stop]
           (2) CORP ACTION — |overnight gap| > corp_gap         [split/bonus guard]
           (3) HOLD DONE   — held >= hold_bars sessions          [the thesis exit]
Portfolio MTM drawdown is monitored by the runner via NT's Portfolio.

Reaction events are precomputed (like HMMConfluenceStrategy's signal table):
config.reaction_events = {ist_date_iso: reaction_float}.
"""
from __future__ import annotations

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.events import PositionOpened, PositionClosed
from nautilus_trader.model.identifiers import InstrumentId, Venue
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy
import pandas as pd

from strategies.pead.manifest import MANIFEST

_P = MANIFEST.params


class PEADStrategyConfig(StrategyConfig, frozen=True):
    # Defaults come from the manifest so the strategy, the live runner, and the
    # research scripts share one source of truth (strategies/pead/manifest.py).
    instrument_id: str
    bar_type: str
    reaction_events: dict          # {ist_date_iso: reaction_float}
    hold_bars: int = _P["hold_bars"]
    stop_pct: float = _P["stop_pct"]    # disaster stop (wide — preserve the drift)
    thresh: float = _P["thresh"]        # |reaction| filter
    corp_gap: float = _P["corp_gap"]    # overnight gap above this = probable corp action
    alloc_pct: float = _P["alloc_pct"]  # equity fraction per position (~3 concurrent)
    max_gross: float = _P["max_gross"]  # portfolio gross-exposure cap


class PEADStrategy(Strategy):
    def __init__(self, config: PEADStrategyConfig) -> None:
        super().__init__(config)
        self._iid = InstrumentId.from_str(config.instrument_id)
        self._bar_type = BarType.from_str(config.bar_type)
        self._venue = Venue(config.instrument_id.split(".")[-1])
        self._events = dict(config.reaction_events)
        self._entry_price: float | None = None
        self._bars_held = 0
        self._prev_close: float | None = None

    def on_start(self) -> None:
        self.subscribe_bars(self._bar_type)

    def on_bar(self, bar: Bar) -> None:
        if bar.bar_type != self._bar_type:
            return
        close = float(bar.close)
        ist_date = (pd.Timestamp(bar.ts_event) + pd.Timedelta(hours=5, minutes=30)).date().isoformat()

        if self.portfolio.is_net_long(self._iid):
            # (2) corporate-action guard — implausible overnight move = split/bonus/etc.
            if self._prev_close and abs(close / self._prev_close - 1) > self.config.corp_gap:
                self.log.info(f"CORP_ACTION_GUARD {self._iid} gap={close/self._prev_close-1:+.1%} — flatten")
                self.close_all_positions(self._iid)
                self._prev_close = close
                return
            # (1) disaster stop
            if self._entry_price and close <= self._entry_price * (1 - self.config.stop_pct):
                self.log.info(f"STOP {self._iid} {close:.2f} <= {self._entry_price*(1-self.config.stop_pct):.2f}")
                self.close_all_positions(self._iid)
                self._prev_close = close
                return
            # (3) hold horizon reached
            self._bars_held += 1
            if self._bars_held >= self.config.hold_bars:
                self.log.info(f"HOLD_EXIT {self._iid} after {self._bars_held} sessions")
                self.close_all_positions(self._iid)
                self._prev_close = close
                return
        else:
            react = self._events.get(ist_date)
            if react is not None and react >= self.config.thresh:   # long-only
                qty = self._size(close)
                if qty > 0 and self._within_gross_limit():
                    self.submit_order(self.order_factory.market(
                        instrument_id=self._iid, order_side=OrderSide.BUY,
                        quantity=Quantity.from_int(qty), time_in_force=TimeInForce.GTC))
                    self._entry_price = close   # approx (fills next open); fine for a wide stop

        self._prev_close = close

    def on_position_opened(self, event: PositionOpened) -> None:
        if event.instrument_id == self._iid:
            self._bars_held = 0

    def on_position_closed(self, event: PositionClosed) -> None:
        if event.instrument_id == self._iid:
            self._entry_price = None
            self._bars_held = 0

    # --- helpers ---
    def _equity(self) -> float:
        try:
            return float(self.portfolio.equity(self._venue).as_decimal())
        except Exception:
            return config.BACKTEST_INITIAL_CAPITAL

    def _size(self, price: float) -> int:
        return int((self._equity() * self.config.alloc_pct) / price) if price > 0 else 0

    def _within_gross_limit(self) -> bool:
        try:
            eq = self._equity()
            if eq <= 0:
                return True
            net = self.portfolio.net_exposures(self._venue) or {}
            gross = sum(abs(float(v)) for v in net.values())
            return gross / eq < self.config.max_gross
        except Exception:
            return True
