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

from core import config

log = logging.getLogger(__name__)

# hmmlearn emits per-fit "Model is not converging" / "zero-sum transition"
# messages through its own logger (not the warnings module). With warm-start
# refits these are benign — EM lands on the prior solution at ~1e-5 delta and
# trips the "not greater" check immediately. Silence them at the source: on a
# rolling backtest they account for 60-80% of all log output.
logging.getLogger("hmmlearn").setLevel(logging.ERROR)


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
        warm_start: bool = False,
    ) -> None:
        self.n_states = n_states
        self.n_iter = n_iter
        self.random_state = random_state
        self._model: GaussianHMM | None = None
        self._state_map: dict[int, str] = {}
        self._scaler: StandardScaler | None = None
        # Warm-start carries the previous fit's params into the next refit,
        # preserving state identity bar-to-bar (the prime cause of regime-label
        # churn) and converging EM in a few iterations. Only valid when every
        # detect_regime() call is the *same* series grown by one bar — i.e. the
        # rolling precompute. Single-shot callers that reuse one instance across
        # different symbols/timeframes (ranker, screener) MUST leave this False.
        self._warm_start = warm_start
        self._warm: dict | None = None
        self._warm_iter = config.HMM_WARM_ITER

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect_regime(self, df: pd.DataFrame, max_window: int | None = None) -> HMMResult:
        """
        Fit the HMM on *df* and return labelled regimes plus the current state.

        Parameters
        ----------
        df         : pd.DataFrame with columns open, high, low, close, volume.
                     Needs at least config.HMM_MIN_SAMPLES rows.
        max_window : if set, only use the last max_window bars for fitting.
                     This improves stationarity but reduces sample size.
                     None = use full window (existing behaviour).
        """
        data = df if max_window is None else df.iloc[-max_window:]

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

    def reset_warm_start(self) -> None:
        """Forget carried-over params (use when fitting an unrelated series)."""
        self._warm = None

    def _fit(self, features: np.ndarray) -> bool:
        warm = self._warm_start and self._warm is not None
        model = GaussianHMM(
            n_components=self.n_states,
            covariance_type="diag",
            n_iter=self._warm_iter if warm else self.n_iter,
            random_state=self.random_state,
            min_covar=1e-3,
            # Warm fits seed all params from the previous solution; tell hmmlearn
            # not to re-initialise them randomly.
            init_params="" if warm else "stmc",
            params="stmc",
        )
        if warm:
            model.startprob_ = self._warm["startprob"]
            model.transmat_ = self._warm["transmat"]
            model.means_ = self._warm["means"]
            model.covars_ = self._warm["covars"]   # diag: shape (n_states, n_features)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model.fit(features)

        self._model = model
        # Preserve state identity across warm fits: only (re)derive labels on a
        # cold fit. Warm fits start from the prior solution, so state k keeps its
        # meaning and the prior label map stays valid.
        if not warm or not self._state_map:
            self._state_map = self._label_states(model)

        # Carry this fit's params forward as the next warm-start seed.
        if self._warm_start:
            self._warm = {
                "startprob": model.startprob_,
                "transmat": model.transmat_,
                "means": model.means_,
                # covars_ getter returns full (n, f, f) matrices; store the diagonal
                # so the setter accepts it back for covariance_type="diag".
                "covars": np.array([np.diag(c) for c in model.covars_]),
            }

        converged = bool(model.monitor_.converged)
        log.debug("HMM fit: warm=%s converged=%s state_map=%s", warm, converged, self._state_map)
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
