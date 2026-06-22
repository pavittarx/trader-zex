"""
ranker.py — Daily multi-factor stock ranking for trade candidate selection.

Ranking factors (configurable weights in config.py)
----------------------------------------------------
  40%  Signal strength       : confluence signal on 15-min bars
  30%  Structure proximity   : how close price is to support (long) / resistance (short)
  20%  Price momentum        : weighted 5-day and 20-day return
  10%  Volume surge          : recent volume vs. 20-day average

Logic
-----
1. Load the Nifty 500 universe (daily-cached in universe.py).
2. Run the Screener on 15-min and 60-min timeframes for all symbols.
3. Fetch 30 days of daily OHLCV for momentum and volume metrics.
4. Compute a composite score for each symbol.
5. Separate long candidates (positive-biased signals, bullish 60-min regime)
   from short candidates (negative-biased signals, bearish 60-min regime).
6. Return top-N of each, cached in ~/.trader_zex_rankings.json.

Usage
-----
    from core.brokers.fyers.client import FyersClient
    from core.operators.ranker import StockRanker

    client = FyersClient()
    ranker = StockRanker(client, n_top=25)
    result = ranker.rank()          # uses disk cache if today's date matches

    print(result.long[:5])          # top 5 long candidates
    print(result.short[:5])         # top 5 short candidates
    print(result.scores_df)         # full scores DataFrame

CLI
---
    uv run python -m ranker          # print today's ranked stocks
    uv run python -m ranker --force  # force re-rank (bypass cache)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import date, timedelta

import pandas as pd

from core import config
from core.brokers.fyers.client import FyersClient, RESAMPLE_RULES, resample_ohlcv
from core.signals.hmm_model import HMMModel
from core.signals.structure import StructureDetector
from core.signals.confluence import generate_signal
from core.operators.universe import get_tradable_universe

log = logging.getLogger(__name__)

# Signal → numeric score for long bias (high = good long, low = bad long)
_LONG_SIGNAL_SCORE: dict[str, float] = {
    "STRONG BUY":  1.0,
    "WEAK BUY":    0.6,
    "WATCH":       0.3,
    "NEUTRAL":     0.0,
    "WAIT":       -0.2,
    "TAKE PROFIT": 0.0,
    "AVOID":      -0.5,
    "STRONG SELL": -1.0,
}
# For shorts: invert — negative long score = good short
_SHORT_SIGNAL_SCORE: dict[str, float] = {k: -v for k, v in _LONG_SIGNAL_SCORE.items()}


@dataclass
class RankedStock:
    symbol: str
    direction: str          # "LONG" or "SHORT"
    composite_score: float
    signal_15m: str
    regime_60m: str
    support: float
    resistance: float
    momentum_5d: float
    volume_surge: float
    proximity_score: float

    def __str__(self) -> str:
        arrow = "▲" if self.direction == "LONG" else "▼"
        return (
            f"{arrow} {self.symbol:<20}  score={self.composite_score:+.3f}"
            f"  sig={self.signal_15m:<12}  regime_60m={self.regime_60m}"
            f"  mom5d={self.momentum_5d:+.1%}  vol_surge={self.volume_surge:.1f}x"
        )


@dataclass
class RankResult:
    long: list[RankedStock] = field(default_factory=list)
    short: list[RankedStock] = field(default_factory=list)
    scores_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    ranked_date: str = ""


class StockRanker:
    """
    Daily multi-factor stock ranker. Results are cached to disk and reused
    within the same calendar day unless force=True is passed to rank().
    """

    def __init__(self, client: FyersClient, n_top: int = config.RANKER_TOP_N) -> None:
        self._client = client
        self._n_top = n_top
        self._hmm = HMMModel()
        self._structure = StructureDetector()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def rank(self, force: bool = False) -> RankResult:
        """
        Return ranked long and short candidates for today.

        Uses disk cache if today's ranking is already saved and force=False.
        """
        if not force:
            cached = self._load_cache()
            if cached is not None:
                log.info("Rankings loaded from cache (%d long, %d short)",
                         len(cached.long), len(cached.short))
                return cached

        symbols = get_tradable_universe()
        log.info("Ranking %d universe symbols …", len(symbols))

        scores_df = self.compute_scores(symbols)
        long_df = scores_df[scores_df["direction"] == "LONG"].sort_values(
            "composite_score", ascending=False
        )
        short_df = scores_df[scores_df["direction"] == "SHORT"].sort_values(
            "composite_score", ascending=False
        )

        long_stocks = [RankedStock(**r) for r in long_df.head(self._n_top).to_dict("records")]
        short_stocks = [RankedStock(**r) for r in short_df.head(self._n_top).to_dict("records")]

        result = RankResult(
            long=long_stocks,
            short=short_stocks,
            scores_df=scores_df,
            ranked_date=date.today().isoformat(),
        )
        self._save_cache(result)
        return result

    def compute_scores(self, symbols: list[str], as_of_date: date | None = None) -> pd.DataFrame:
        """
        Compute per-symbol multi-factor composite scores.

        Parameters
        ----------
        symbols :
            List of Fyers symbol strings to score.
        as_of_date :
            If provided, fetch data strictly up to this date (point-in-time).
            Defaults to None, which fetches up to today.

        Returns a DataFrame with one row per symbol and columns:
            symbol, direction, composite_score, signal_15m, regime_60m,
            support, resistance, momentum_5d, volume_surge, proximity_score,
            plus individual factor scores.
        """
        signal_map = self._fetch_signals(symbols, as_of_date=as_of_date)
        momentum_map = self._fetch_momentum(symbols, as_of_date=as_of_date)

        rows = []
        for sym in symbols:
            row = self._score(sym, signal_map, momentum_map)
            if row is not None:
                rows.append(row)

        if not rows:
            return pd.DataFrame()

        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # Factor computation
    # ------------------------------------------------------------------

    def _fetch_signals(self, symbols: list[str], as_of_date: date | None = None) -> dict[str, dict]:
        """
        Fetch 15-min and 60-min signals for all symbols using the same
        batching strategy as Screener: one 1-min fetch per symbol → resample.

        Parameters
        ----------
        symbols :
            List of Fyers symbol strings to fetch.
        as_of_date :
            If provided, fetch data strictly up to this date (point-in-time).
            Defaults to None, which fetches up to today.

        Returns {symbol: {signal_15m, regime_15m, regime_60m, support,
                          resistance, location, support_dist_pct,
                          resistance_dist_pct}}
        """
        result: dict[str, dict] = {}
        total = len(symbols)
        date_to = as_of_date or date.today()
        date_from = date_to - timedelta(days=config.LOOKBACK_DAYS.get("1", 30))
        for i, sym in enumerate(symbols, 1):
            log.info("[%d/%d] Fetching signals: %s", i, total, sym)
            try:
                base = self._client.get_history(sym, "1", date_from=date_from, date_to=date_to)
                if base.empty:
                    continue

                df_15m = resample_ohlcv(base, RESAMPLE_RULES["15"])
                df_60m = resample_ohlcv(base, RESAMPLE_RULES["60"])

                if len(df_15m) < config.HMM_MIN_SAMPLES:
                    continue

                hmm_15 = self._hmm.detect_regime(df_15m)
                struct = self._structure.detect(df_15m)
                signal = generate_signal(hmm_15.current_regime, struct.location)

                if len(df_60m) >= config.HMM_MIN_SAMPLES:
                    hmm_60 = self._hmm.detect_regime(df_60m)
                    regime_60 = hmm_60.current_regime
                else:
                    regime_60 = hmm_15.current_regime

                result[sym] = {
                    "signal_15m": signal,
                    "regime_15m": hmm_15.current_regime,
                    "regime_60m": regime_60,
                    "support": struct.support,
                    "resistance": struct.resistance,
                    "location": struct.location,
                    "support_dist_pct": struct.support_dist_pct,
                    "resistance_dist_pct": struct.resistance_dist_pct,
                }

            except Exception as exc:
                log.debug("Signal fetch failed for %s: %s", sym, exc)

        success = len(result)
        failed = len(symbols) - success
        log.info(
            "Signal fetch complete: %d/%d symbols succeeded, %d failed/skipped",
            success, len(symbols), failed,
        )
        return result

    def _fetch_momentum(self, symbols: list[str], as_of_date: date | None = None) -> dict[str, dict]:
        """
        Fetch 30 days of daily bars for all symbols and compute:
          - 5-day price return
          - volume surge (5-day avg volume / 20-day avg volume)

        Parameters
        ----------
        symbols :
            List of Fyers symbol strings to fetch.
        as_of_date :
            If provided, fetch data strictly up to this date (point-in-time).
            Defaults to None, which fetches up to today.

        Returns {symbol: {momentum_5d, volume_surge}}
        """
        result: dict[str, dict] = {}
        date_to = as_of_date or date.today()
        date_from = date_to - timedelta(days=35)

        daily_data = self._client.get_history_multi(
            symbols, resolution="D", date_from=date_from, date_to=date_to
        )

        for sym, df in daily_data.items():
            if df.empty or len(df) < 6:
                result[sym] = {"momentum_5d": 0.0, "volume_surge": 1.0}
                continue

            close = df["close"]
            volume = df["volume"]

            mom_5d = float(close.iloc[-1] / close.iloc[-6] - 1) if len(close) >= 6 else 0.0

            avg_vol_20 = volume.iloc[-21:-1].mean() if len(volume) >= 21 else volume.mean()
            today_vol = volume.iloc[-1]
            vol_surge = float(today_vol / avg_vol_20) if avg_vol_20 > 0 else 1.0

            result[sym] = {
                "momentum_5d": mom_5d,
                "volume_surge": min(vol_surge, 5.0),   # cap at 5× to limit outlier impact
            }

        return result

    def _score(
        self,
        sym: str,
        signal_map: dict[str, dict],
        momentum_map: dict[str, dict],
    ) -> dict | None:
        sig_data = signal_map.get(sym)
        mom_data = momentum_map.get(sym, {"momentum_5d": 0.0, "volume_surge": 1.0})

        if sig_data is None:
            return None

        signal_15m = sig_data["signal_15m"]
        regime_60m = sig_data["regime_60m"]
        location = sig_data["location"]
        support_dist = sig_data["support_dist_pct"]
        resistance_dist = sig_data["resistance_dist_pct"]

        # Direction is driven by 60-min regime
        if regime_60m == "Bullish":
            direction = "LONG"
        elif regime_60m == "Bearish":
            direction = "SHORT"
        else:
            # Sideways: let the 15-min signal decide direction
            # Positive-biased signals → LONG; negative-biased → SHORT
            _LONG_BIASED = {"STRONG BUY", "WEAK BUY", "WATCH", "TAKE PROFIT"}
            _SHORT_BIASED = {"STRONG SELL", "AVOID", "WAIT"}
            if signal_15m in _SHORT_BIASED:
                direction = "SHORT"
            else:
                direction = "LONG"  # NEUTRAL / WATCH → lean long

        # --- Factor 1: Signal strength (normalised to [-1, 1]) ---
        if direction == "LONG":
            sig_score = _LONG_SIGNAL_SCORE.get(signal_15m, 0.0)
        else:
            sig_score = _SHORT_SIGNAL_SCORE.get(signal_15m, 0.0)

        # --- Factor 2: Structure proximity ---
        # Closer to support (long) / resistance (short) = higher score
        # Score is 1.0 when at S/R, 0 at 5× proximity threshold, negative beyond
        prox = config.STRUCTURE_PROXIMITY_PCT
        if direction == "LONG":
            prox_score = 1.0 - support_dist / (prox * 5)
            prox_score = max(-1.0, min(1.0, prox_score))  # clamp to [-1, 1]
        else:
            prox_score = 1.0 - resistance_dist / (prox * 5)
            prox_score = max(-1.0, min(1.0, prox_score))

        # --- Factor 3: Momentum (normalised, long wants positive, short wants negative) ---
        mom_5d = mom_data["momentum_5d"]
        mom_score_raw = float(pd.Series([mom_5d]).clip(-0.10, 0.10).iloc[0] / 0.10)
        mom_score = mom_score_raw if direction == "LONG" else -mom_score_raw

        # --- Factor 4: Volume surge — signed by price direction ---
        # Up-volume confirms long; down-volume (selling climax) penalises long
        vol_surge = mom_data["volume_surge"]
        vol_direction = 1.0 if mom_5d >= 0 else -1.0
        vol_score_raw = min(vol_surge / 3.0, 1.0)
        # For long candidates: up-volume is good, down-volume is bad
        # For short candidates: invert
        if direction == "LONG":
            vol_score = vol_score_raw * vol_direction
        else:
            vol_score = vol_score_raw * (-vol_direction)

        w = {
            "signal":    config.RANKER_WEIGHT_SIGNAL,
            "structure": config.RANKER_WEIGHT_STRUCTURE,
            "momentum":  config.RANKER_WEIGHT_MOMENTUM,
            "volume":    config.RANKER_WEIGHT_VOLUME,
        }
        composite = (
            w["signal"]    * sig_score +
            w["structure"] * prox_score +
            w["momentum"]  * mom_score +
            w["volume"]    * vol_score
        )

        return {
            "symbol": sym,
            "direction": direction,
            "composite_score": round(composite, 4),
            "signal_15m": signal_15m,
            "regime_60m": regime_60m,
            "support": sig_data["support"],
            "resistance": sig_data["resistance"],
            "momentum_5d": round(mom_5d, 4),
            "volume_surge": round(vol_surge, 2),
            "proximity_score": round(prox_score, 4),
            # Individual factor scores for inspection
            "score_signal": round(sig_score, 4),
            "score_momentum": round(mom_score, 4),
            "score_volume": round(vol_score, 4),
        }

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _load_cache(self) -> RankResult | None:
        path = config.RANKER_CACHE_FILE
        try:
            data = json.loads(path.read_text())
            if data.get("date") != date.today().isoformat():
                return None

            def _parse(records: list[dict]) -> list[RankedStock]:
                return [RankedStock(**r) for r in records]

            return RankResult(
                long=_parse(data.get("long", [])),
                short=_parse(data.get("short", [])),
                ranked_date=data.get("date", ""),
            )
        except Exception as exc:
            log.debug("Ranking cache read failed: %s", exc)
            return None

    def _save_cache(self, result: RankResult) -> None:
        path = config.RANKER_CACHE_FILE
        try:
            payload = {
                "date": date.today().isoformat(),
                "long": [asdict(r) for r in result.long],
                "short": [asdict(r) for r in result.short],
            }
            path.write_text(json.dumps(payload, indent=2))
            log.debug("Rankings cached to %s", path)
        except Exception as exc:
            log.warning("Could not save rankings cache: %s", exc)


# ------------------------------------------------------------------
# CLI (python -m ranker)
# ------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="Daily stock ranker")
    parser.add_argument("--force", action="store_true", help="Bypass cache and re-rank")
    parser.add_argument("--top-n", type=int, default=config.RANKER_TOP_N,
                        help="Number of candidates per side")
    args = parser.parse_args()

    from core.brokers.fyers.client import FyersClient
    client = FyersClient()
    ranker = StockRanker(client, n_top=args.top_n)
    result = ranker.rank(force=args.force)

    print(f"\n{'='*70}")
    print(f"  RANKED STOCKS — {date.today()}  (top {args.top_n} per side)")
    print(f"{'='*70}")

    print(f"\n  LONG CANDIDATES ({len(result.long)})")
    print(f"  {'─'*65}")
    for r in result.long:
        print(f"  {r}")

    print(f"\n  SHORT CANDIDATES ({len(result.short)})")
    print(f"  {'─'*65}")
    for r in result.short:
        print(f"  {r}")

    print()
    sys.exit(0)
