"""
test_instruments.py — Tests for backtest/instruments.py.

Covers:
  - fyers_to_instrument_id: correct symbol and venue parsing
  - make_equity: non-zero maker_fee and taker_fee, correct currency
"""
import pytest

nautilus_trader = pytest.importorskip("nautilus_trader")

from decimal import Decimal

from core.backtest.instruments import fyers_to_instrument_id, make_equity
from core import config


class TestFyersToInstrumentId:
    def test_symbol_parsed_correctly(self):
        iid = fyers_to_instrument_id("NSE:RELIANCE-EQ")
        assert iid.symbol.value == "RELIANCE-EQ"

    def test_venue_parsed_correctly(self):
        iid = fyers_to_instrument_id("NSE:RELIANCE-EQ")
        assert iid.venue.value == "NSE"

    def test_string_round_trip(self):
        """The InstrumentId string form should be 'RELIANCE-EQ.NSE'."""
        iid = fyers_to_instrument_id("NSE:RELIANCE-EQ")
        assert str(iid) == "RELIANCE-EQ.NSE"

    def test_different_symbol(self):
        iid = fyers_to_instrument_id("NSE:TCS-EQ")
        assert iid.symbol.value == "TCS-EQ"
        assert iid.venue.value == "NSE"

    def test_venue_always_nse(self):
        for sym in ["NSE:INFY-EQ", "NSE:HDFCBANK-EQ", "NSE:SBIN-EQ"]:
            iid = fyers_to_instrument_id(sym)
            assert iid.venue.value == "NSE"


class TestMakeEquity:
    @pytest.fixture
    def reliance_equity(self):
        return make_equity("NSE:RELIANCE-EQ")

    def test_maker_fee_nonzero(self, reliance_equity):
        """Buy-leg commission must be > 0."""
        assert reliance_equity.maker_fee > Decimal("0")

    def test_taker_fee_nonzero(self, reliance_equity):
        """Sell-leg commission must be > 0."""
        assert reliance_equity.taker_fee > Decimal("0")

    def test_maker_fee_matches_config(self, reliance_equity):
        expected = Decimal(str(round(config.BACKTEST_COMMISSION_BUY, 6)))
        assert reliance_equity.maker_fee == expected

    def test_taker_fee_matches_config(self, reliance_equity):
        expected = Decimal(str(round(config.BACKTEST_COMMISSION_SELL, 6)))
        assert reliance_equity.taker_fee == expected

    def test_sell_fee_greater_than_buy_fee(self, reliance_equity):
        """STT on sell leg means sell commission > buy commission."""
        assert reliance_equity.taker_fee > reliance_equity.maker_fee

    def test_currency_is_inr(self, reliance_equity):
        from nautilus_trader.model.currencies import INR
        # NT 1.226: Equity exposes currency via quote_currency
        assert reliance_equity.quote_currency == INR

    def test_price_precision_is_2(self, reliance_equity):
        assert reliance_equity.price_precision == 2

    def test_instrument_id_matches(self, reliance_equity):
        assert reliance_equity.id.symbol.value == "RELIANCE-EQ"
        assert reliance_equity.id.venue.value == "NSE"
