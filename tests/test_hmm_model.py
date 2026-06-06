"""
test_hmm_model.py — Tests for hmm_model.HMMModel.

Covers:
  - detect_regime() returns HMMResult with valid .current_regime label
  - .states Series length matches number of feature rows (n_bars - 1)
  - .state_map has exactly 3 entries mapping to the 3 regime labels
  - Raises ValueError with < HMM_MIN_SAMPLES bars
  - HMMResult.converged is a bool

All HMM tests are marked @pytest.mark.slow because the GaussianHMM fit
may take a few seconds. Run them with: uv run pytest tests/ -v -m slow
The default test run (without -m slow) skips them.
"""
import numpy as np
import pandas as pd
import pytest

from core import config
from core.hmm_model import HMMModel, HMMResult

EXPECTED_REGIMES = {"Bullish", "Sideways", "Bearish"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ohlcv(n: int, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic OHLCV data with n bars."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-02 09:15", periods=n, freq="15min")

    log_returns = rng.normal(0.0002, 0.005, n)
    close = 100.0 * np.exp(np.cumsum(log_returns))

    half_range = np.abs(rng.normal(0, 0.3, n)) + 0.05
    high = close + half_range
    low = close - half_range
    open_ = np.clip(close + rng.normal(0, 0.2, n), low, high)

    volume = rng.integers(5_000, 50_000, n).astype(float)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestHMMModelRegime:
    @pytest.fixture(scope="class")
    def hmm_result(self):
        """Fit HMM once for the whole class — reuse across tests."""
        df = _make_ohlcv(config.HMM_MIN_SAMPLES + 10)
        model = HMMModel()
        return model.detect_regime(df)

    def test_returns_hmm_result(self, hmm_result):
        assert isinstance(hmm_result, HMMResult)

    def test_current_regime_is_valid(self, hmm_result):
        assert hmm_result.current_regime in EXPECTED_REGIMES

    def test_state_map_has_three_entries(self, hmm_result):
        assert len(hmm_result.state_map) == 3

    def test_state_map_values_are_regime_labels(self, hmm_result):
        assert set(hmm_result.state_map.values()) == EXPECTED_REGIMES

    def test_states_series_has_correct_length(self, hmm_result):
        """States should have n_bars - 1 rows (first row lost to log-return diff)."""
        n = config.HMM_MIN_SAMPLES + 10
        assert len(hmm_result.states) == n - 1

    def test_states_contain_only_valid_labels(self, hmm_result):
        assert set(hmm_result.states.unique()).issubset(EXPECTED_REGIMES)

    def test_converged_is_bool(self, hmm_result):
        assert isinstance(hmm_result.converged, bool)

    def test_current_regime_matches_last_state(self, hmm_result):
        assert hmm_result.current_regime == hmm_result.states.iloc[-1]


@pytest.mark.slow
class TestHMMModelWithFixture:
    """Use the shared sample_ohlcv_df fixture (210 bars)."""

    def test_detect_regime_with_200_bars(self, sample_ohlcv_df):
        model = HMMModel()
        result = model.detect_regime(sample_ohlcv_df)
        assert result.current_regime in EXPECTED_REGIMES

    def test_states_index_aligned_to_input(self, sample_ohlcv_df):
        """State Series index should be a subset of the input index."""
        model = HMMModel()
        result = model.detect_regime(sample_ohlcv_df)
        # All state timestamps must exist in the input index
        assert result.states.index.isin(sample_ohlcv_df.index).all()


@pytest.mark.slow
class TestHMMModelEdgeCases:
    def test_raises_value_error_below_min_samples(self):
        """< HMM_MIN_SAMPLES bars must raise ValueError."""
        df = _make_ohlcv(config.HMM_MIN_SAMPLES - 1)
        model = HMMModel()
        with pytest.raises(ValueError, match="at least"):
            model.detect_regime(df)

    def test_exactly_min_samples_does_not_raise(self):
        """Exactly HMM_MIN_SAMPLES bars should succeed."""
        df = _make_ohlcv(config.HMM_MIN_SAMPLES)
        model = HMMModel()
        result = model.detect_regime(df)
        assert result.current_regime in EXPECTED_REGIMES

    def test_error_message_includes_min_samples(self):
        df = _make_ohlcv(config.HMM_MIN_SAMPLES - 10)
        model = HMMModel()
        with pytest.raises(ValueError) as exc_info:
            model.detect_regime(df)
        assert str(config.HMM_MIN_SAMPLES) in str(exc_info.value)

    def test_different_seeds_produce_valid_regimes(self):
        """Robustness: different random data still yields valid regime labels."""
        for seed in [0, 1, 7, 99]:
            df = _make_ohlcv(config.HMM_MIN_SAMPLES + 20, seed=seed)
            model = HMMModel()
            result = model.detect_regime(df)
            assert result.current_regime in EXPECTED_REGIMES, (
                f"Seed {seed}: unexpected regime {result.current_regime!r}"
            )
