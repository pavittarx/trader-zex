"""
test_confluence.py — Tests for confluence.generate_signal().

Covers:
  - All 9 valid (regime, location) combinations return a non-empty string
  - Specific critical mappings (STRONG BUY, STRONG SELL)
  - Invalid inputs return "NEUTRAL" (fallback via .get default)
"""
import pytest

from core.confluence import generate_signal, _SIGNAL_TABLE


# ---------------------------------------------------------------------------
# All 9 cells
# ---------------------------------------------------------------------------


class TestAllCells:
    @pytest.mark.parametrize("regime,location,expected", [
        ("Bullish",  "At Support",    "STRONG BUY"),
        ("Bullish",  "In Middle",     "WEAK BUY"),
        ("Bullish",  "At Resistance", "TAKE PROFIT"),
        ("Sideways", "At Support",    "WATCH"),
        ("Sideways", "In Middle",     "NEUTRAL"),
        ("Sideways", "At Resistance", "WATCH"),
        ("Bearish",  "At Support",    "WAIT"),
        ("Bearish",  "In Middle",     "AVOID"),
        ("Bearish",  "At Resistance", "STRONG SELL"),
    ])
    def test_cell(self, regime, location, expected):
        assert generate_signal(regime, location) == expected

    def test_all_cells_return_nonempty_string(self):
        for (regime, location) in _SIGNAL_TABLE:
            result = generate_signal(regime, location)
            assert isinstance(result, str)
            assert len(result) > 0

    def test_signal_table_has_nine_entries(self):
        assert len(_SIGNAL_TABLE) == 9


# ---------------------------------------------------------------------------
# Critical specific mappings
# ---------------------------------------------------------------------------


class TestCriticalMappings:
    def test_strong_buy(self):
        assert generate_signal("Bullish", "At Support") == "STRONG BUY"

    def test_strong_sell(self):
        assert generate_signal("Bearish", "At Resistance") == "STRONG SELL"

    def test_neutral_in_sideways_middle(self):
        assert generate_signal("Sideways", "In Middle") == "NEUTRAL"

    def test_take_profit_bullish_at_resistance(self):
        assert generate_signal("Bullish", "At Resistance") == "TAKE PROFIT"

    def test_avoid_bearish_middle(self):
        assert generate_signal("Bearish", "In Middle") == "AVOID"


# ---------------------------------------------------------------------------
# Invalid inputs
# ---------------------------------------------------------------------------


class TestInvalidInputs:
    def test_invalid_regime_returns_neutral(self):
        """Unknown regime → falls back to "NEUTRAL" via dict .get default."""
        assert generate_signal("Unknown", "At Support") == "NEUTRAL"

    def test_invalid_location_returns_neutral(self):
        assert generate_signal("Bullish", "Somewhere") == "NEUTRAL"

    def test_both_invalid_returns_neutral(self):
        assert generate_signal("None", "None") == "NEUTRAL"

    def test_empty_strings_return_neutral(self):
        assert generate_signal("", "") == "NEUTRAL"

    def test_case_sensitive_regime(self):
        """Regime labels are case-sensitive; lowercase 'bullish' is not valid."""
        assert generate_signal("bullish", "At Support") == "NEUTRAL"
