"""
instruments.py — NSE equity instrument definitions for NautilusTrader.

Fyers symbol format:  "NSE:RELIANCE-EQ"
NT InstrumentId:      Symbol("RELIANCE-EQ") @ Venue("NSE")
"""

from decimal import Decimal

from nautilus_trader.model.currencies import INR
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.objects import Price, Quantity

import config

NSE_VENUE = Venue("NSE")


def fyers_to_instrument_id(fyers_sym: str) -> InstrumentId:
    """'NSE:RELIANCE-EQ' → InstrumentId(Symbol('RELIANCE-EQ'), Venue('NSE'))"""
    _, ticker = fyers_sym.split(":", 1)
    return InstrumentId(Symbol(ticker), NSE_VENUE)


def make_equity(fyers_sym: str, commission: float = config.BACKTEST_COMMISSION) -> Equity:
    """Create a NautilusTrader Equity instrument for an NSE stock."""
    instrument_id = fyers_to_instrument_id(fyers_sym)
    fee = Decimal(str(round(commission, 6)))
    return Equity(
        instrument_id=instrument_id,
        raw_symbol=Symbol(instrument_id.symbol.value),
        currency=INR,
        price_precision=2,
        price_increment=Price.from_str("0.05"),  # NSE min tick = 5 paise
        lot_size=Quantity.from_int(1),
        ts_event=0,
        ts_init=0,
        maker_fee=fee,
        taker_fee=fee,
    )
