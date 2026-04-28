"""
HMMModel — wraps hmmlearn.GaussianHMM to detect 3 market regimes from OHLCV data.

Features fed to the model
--------------------------
1. Log return   : log(close[t] / close[t-1])    — direction / momentum
2. Range ratio  : (high - low) / close          — intra-bar volatility proxy

State labelling
---------------
States are ranked by a composite score:  mean_return − mean_volatility
  highest score → Bullish  (strong return, contained vol)
  lowest  score → Bearish  (weak/negative return, elevated vol)
  middle  score → Sideways (muted return, moderate vol)

Both features are standardised before fitting so neither dominates the
covariance matrix numerically.
"""

import logging
import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM
from sklearn.preprocessing import StandardScaler

import config

log = logging.getLogger(__name__)


@dataclass
class HMMResult:
    """Container returned by HMMModel.detect_regime()."""
    states: pd.Series           # labelled regime per bar, aligned to input index
    current_regime: str         # regime label for the most recent bar
    state_map: dict[int, str]   # raw HMM state index → human label
    converged: bool             # whether the EM algorithm converged


class HMMModel:
    """Fit a 3-state Gaussian HMM and label regimes as Bullish / Sideways / Bearish."""

    def __init__(
        self,
        n_states: int = config.HMM_N_STATES,
        n_iter: int = config.HMM_N_ITER,
        random_state: int = config.HMM_RANDOM_STATE,
    ) -> None:
        self.n_states = n_states
        self.n_iter = n_iter
        self.random_state = random_state
        self._model: GaussianHMM | None = None
        self._state_map: dict[int, str] = {}
        self._scaler: StandardScaler | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect_regime(self, data: pd.DataFrame) -> HMMResult:
        """
        Fit the HMM on *data* and return labelled regimes plus the current state.

        Parameters
        ----------
        data : pd.DataFrame with columns open, high, low, close, volume.
               Needs at least config.HMM_MIN_SAMPLES rows.
        """
        if len(data) < config.HMM_MIN_SAMPLES:
            raise ValueError(
                f"Need at least {config.HMM_MIN_SAMPLES} bars to fit the HMM, "
                f"got {len(data)}."
            )

        features, valid_index = self._build_features(data)
        converged = self._fit(features)
        raw_states = self._model.predict(features)

        labelled = pd.Series(
            [self._state_map[int(s)] for s in raw_states],
            index=valid_index,
            name="regime",
        )

        return HMMResult(
            states=labelled,
            current_regime=labelled.iloc[-1],
            state_map=dict(self._state_map),
            converged=converged,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_features(self, data: pd.DataFrame) -> tuple[np.ndarray, pd.Index]:
        log_ret = np.log(data["close"] / data["close"].shift(1)).dropna()
        range_ratio = ((data["high"] - data["low"]) / data["close"]).loc[log_ret.index]
        raw = np.column_stack([log_ret.values, range_ratio.values])

        self._scaler = StandardScaler()
        scaled = self._scaler.fit_transform(raw)
        return scaled, log_ret.index

    def _fit(self, features: np.ndarray) -> bool:
        model = GaussianHMM(
            n_components=self.n_states,
            covariance_type="diag",
            n_iter=self.n_iter,
            random_state=self.random_state,
            min_covar=1e-3,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model.fit(features)

        self._model = model
        self._state_map = self._label_states(model)
        converged = bool(model.monitor_.converged)
        log.debug("HMM fit: converged=%s  state_map=%s", converged, self._state_map)
        return converged

    @staticmethod
    def _label_states(model: GaussianHMM) -> dict[int, str]:
        """
        Composite score per state: mean_return − mean_volatility.

        In standardised space:
          - A state with high mean return AND low mean volatility scores highest → Bullish.
          - A state with low/negative return AND high volatility scores lowest  → Bearish.
          - The middle state                                                     → Sideways.
        """
        mean_ret = model.means_[:, 0]       # standardised log-return mean
        mean_vol = model.means_[:, 1]       # standardised range-ratio mean
        score = mean_ret - mean_vol

        ranked = np.argsort(score)          # ascending → [most-bearish … most-bullish]
        return {
            int(ranked[2]): "Bullish",
            int(ranked[1]): "Sideways",
            int(ranked[0]): "Bearish",
        }
