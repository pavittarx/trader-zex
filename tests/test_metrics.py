"""
test_metrics.py — Tests for backtest/metrics.py._from_positions().

Covers:
  - PnL string parsing: "2910.00 INR" → 2910.0, "0.00 INR" → 0.0
  - win_rate_pct calculation
  - max_drawdown_inr calculation
  - profit_factor calculation
  - Empty / missing columns handled gracefully
"""
import pandas as pd
import pytest

from backtest.metrics import _from_positions


# ---------------------------------------------------------------------------
# PnL string parsing
# ---------------------------------------------------------------------------


class TestPnlParsing:
    def test_parses_positive_pnl(self):
        df = pd.DataFrame({"realized_pnl": ["2910.00 INR"]})
        result = _from_positions(df)
        assert result["total_pnl_inr"] == pytest.approx(2910.0)

    def test_parses_zero_pnl(self):
        df = pd.DataFrame({"realized_pnl": ["0.00 INR"]})
        result = _from_positions(df)
        assert result["total_pnl_inr"] == pytest.approx(0.0)

    def test_parses_negative_pnl(self):
        df = pd.DataFrame({"realized_pnl": ["-500.00 INR"]})
        result = _from_positions(df)
        assert result["total_pnl_inr"] == pytest.approx(-500.0)

    def test_total_pnl_is_sum(self):
        df = pd.DataFrame({"realized_pnl": ["2910.00 INR", "-500.00 INR", "0.00 INR"]})
        result = _from_positions(df)
        assert result["total_pnl_inr"] == pytest.approx(2410.0)


# ---------------------------------------------------------------------------
# Win rate
# ---------------------------------------------------------------------------


class TestWinRate:
    def test_50_pct_when_one_win_one_loss(self):
        df = pd.DataFrame({"realized_pnl": ["500.00 INR", "-500.00 INR"]})
        result = _from_positions(df)
        assert result["win_rate_pct"] == pytest.approx(50.0)

    def test_100_pct_when_all_wins(self):
        df = pd.DataFrame({"realized_pnl": ["100.00 INR", "200.00 INR", "50.00 INR"]})
        result = _from_positions(df)
        assert result["win_rate_pct"] == pytest.approx(100.0)

    def test_0_pct_when_all_losses(self):
        df = pd.DataFrame({"realized_pnl": ["-100.00 INR", "-200.00 INR"]})
        result = _from_positions(df)
        assert result["win_rate_pct"] == pytest.approx(0.0)

    def test_breakeven_trades_count_as_losses(self):
        """Trades with pnl == 0 are neither wins nor losses in win rate."""
        df = pd.DataFrame({"realized_pnl": ["100.00 INR", "0.00 INR"]})
        result = _from_positions(df)
        # 1 win out of 2 trades = 50.0
        assert result["win_rate_pct"] == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# Max drawdown
# ---------------------------------------------------------------------------


class TestMaxDrawdown:
    def test_drawdown_known_sequence(self):
        """
        Cumulative P&L: [100, 50, 150, 75]
        Running max:    [100, 100, 150, 150]
        Drawdown:       [  0, -50,   0, -75]
        Min drawdown = -75.0  (the 150 → 75 drop)
        """
        df = pd.DataFrame({"realized_pnl": ["100.00 INR", "-50.00 INR", "100.00 INR", "-75.00 INR"]})
        result = _from_positions(df)
        assert result["max_drawdown_inr"] == pytest.approx(-75.0)

    def test_no_drawdown_when_always_going_up(self):
        df = pd.DataFrame({"realized_pnl": ["10.00 INR", "20.00 INR", "30.00 INR"]})
        result = _from_positions(df)
        assert result["max_drawdown_inr"] == pytest.approx(0.0)

    def test_drawdown_is_non_positive(self):
        """Drawdown is always <= 0 by definition."""
        df = pd.DataFrame({"realized_pnl": ["100.00 INR", "-200.00 INR", "50.00 INR"]})
        result = _from_positions(df)
        assert result["max_drawdown_inr"] <= 0.0


# ---------------------------------------------------------------------------
# Profit factor
# ---------------------------------------------------------------------------


class TestProfitFactor:
    def test_profit_factor_basic(self):
        """profit_factor = gross_wins / abs(gross_losses) = 2910 / 500 = 5.82."""
        df = pd.DataFrame({"realized_pnl": ["2910.00 INR", "-500.00 INR"]})
        result = _from_positions(df)
        assert result["profit_factor"] == pytest.approx(5.82, rel=1e-2)

    def test_profit_factor_none_when_no_losses(self):
        """profit_factor is None when there are no losses (avoid division by zero)."""
        df = pd.DataFrame({"realized_pnl": ["500.00 INR", "300.00 INR"]})
        result = _from_positions(df)
        assert result.get("profit_factor") is None


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_df_returns_empty_dict(self):
        result = _from_positions(pd.DataFrame())
        assert result == {}

    def test_missing_realized_pnl_column_returns_empty_dict(self):
        df = pd.DataFrame({"instrument_id": ["RELIANCE-EQ.NSE"]})
        result = _from_positions(df)
        assert result == {}

    def test_instrument_id_filter(self):
        """When instrument_id is provided, only matching rows are included."""
        df = pd.DataFrame(
            {
                "instrument_id": ["RELIANCE-EQ.NSE", "TCS-EQ.NSE"],
                "realized_pnl": ["1000.00 INR", "500.00 INR"],
            }
        )
        result = _from_positions(df, instrument_id="RELIANCE-EQ.NSE")
        assert result["total_pnl_inr"] == pytest.approx(1000.0)

    def test_single_trade(self):
        df = pd.DataFrame({"realized_pnl": ["250.00 INR"]})
        result = _from_positions(df)
        assert result["total_pnl_inr"] == pytest.approx(250.0)
        assert result["win_rate_pct"] == pytest.approx(100.0)
        assert result["max_drawdown_inr"] == pytest.approx(0.0)
