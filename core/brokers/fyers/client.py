"""
FyersClient — authenticated wrapper around fyers_apiv3.fyersModel.FyersModel.

Responsibilities:
  - Create and hold an authenticated session.
  - Fetch historical OHLCV bars for a symbol + resolution.
  - Return clean pandas DataFrames with a DatetimeIndex (IST-aware).
  - Enforce API rate limits via configurable sleep between requests.
"""

import logging
import time
from datetime import date, timedelta

import pandas as pd
from fyers_apiv3 import fyersModel

from core.brokers.fyers import auth
from core import config

log = logging.getLogger(__name__)

_OHLCV_COLS = ["datetime", "open", "high", "low", "close", "volume"]

# Resolutions that can be derived by resampling 1-min data
INTRADAY_RESOLUTIONS: frozenset[str] = frozenset(
    {"1", "2", "3", "5", "10", "15", "20", "30", "60", "120", "240"}
)
EOD_RESOLUTIONS: frozenset[str] = frozenset({"D", "W", "M"})

# Maps Fyers resolution string → pandas resample offset alias
RESAMPLE_RULES: dict[str, str] = {
    "1": "1min",
    "2": "2min",
    "3": "3min",
    "5": "5min",
    "10": "10min",
    "15": "15min",
    "20": "20min",
    "30": "30min",
    "60": "1h",
    "120": "2h",
    "240": "4h",
    "D": "D",
    "W": "W-FRI",  # week ending Friday (NSE)
    "M": "MS",  # month start
}


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """
    Resample a 1-min OHLCV DataFrame to a coarser timeframe.

    Open  = first tick in the period
    High  = highest tick
    Low   = lowest tick
    Close = last tick
    Volume= sum of all ticks  ← must be summed, never averaged

    Empty periods (outside market hours, weekends) are dropped.
    """
    resampled = df.resample(rule, closed="left", label="left").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    # Drop bars with no trades (non-trading periods have NaN close and zero volume)
    return resampled.dropna(subset=["close"]).loc[resampled["volume"] > 0]


class FyersClient:
    def __init__(self, access_token: str | None = None, require_headless: bool = False) -> None:
        """
        Initialize authenticated Fyers client.
        
        Parameters
        ----------
        access_token : str | None
            Explicit token. If None, login() is called (cache → headless → interactive).
        require_headless : bool
            If True, require headless (TOTP) auth; fail if env vars missing.
            Useful for EC2/sandbox/CI to prevent interactive prompts.
        """
        if access_token is None:
            access_token = auth.login(require_headless=require_headless)

        self._fyers = fyersModel.FyersModel(
            client_id=config.FYERS_CLIENT_ID,
            token=access_token,
            log_path="",  # suppress verbose SDK file-logging
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def get_history(
        self,
        symbol: str,
        resolution: str,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        cont_flag: int = 1,
    ) -> pd.DataFrame:
        """
        Fetch OHLCV history for *symbol* at *resolution*.

        Parameters
        ----------
        symbol      : Fyers symbol string, e.g. ``"NSE:RELIANCE-EQ"``
        resolution  : ``"1"``, ``"5"``, ``"15"``, ``"60"``, ``"D"``, ``"W"``, ``"M"`` …
        date_from   : start date — defaults to a resolution-specific lookback
        date_to     : end date   — defaults to today
        cont_flag   : 1 = continuous (futures); 0 = non-continuous

        Returns
        -------
        pd.DataFrame
            Columns: open, high, low, close, volume.
            Index: DatetimeIndex (IST timezone-naive for intraday; date-only for EOD+).
        """
        if date_to is None:
            date_to = date.today()
        if date_from is None:
            lookback = config.LOOKBACK_DAYS.get(resolution, 365)
            date_from = date_to - timedelta(days=lookback)

        payload = {
            "symbol": symbol,
            "resolution": resolution,
            "date_format": "1",  # epoch timestamps
            "range_from": date_from.strftime("%Y-%m-%d"),
            "range_to": date_to.strftime("%Y-%m-%d"),
            "cont_flag": str(cont_flag),
        }

        log.debug("Fetching %s @ %s  [%s → %s]", symbol, resolution, date_from, date_to)
        response = self._fyers.history(payload)

        if response.get("s") != "ok":
            raise RuntimeError(
                f"History API error for {symbol} @ {resolution}: {response}"
            )

        candles = response.get("candles", [])
        if not candles:
            log.warning("No candles returned for %s @ %s", symbol, resolution)
            return pd.DataFrame(columns=_OHLCV_COLS[1:])

        df = pd.DataFrame(candles, columns=_OHLCV_COLS)
        df = self._parse_timestamps(df, resolution)
        df = df.drop_duplicates(subset=["datetime"]).set_index("datetime").sort_index()
        return df

    def get_quotes(self, symbols: list[str]) -> pd.DataFrame:
        """
        Fetch last traded price and change% for *symbols* in a single API call.

        Returns
        -------
        pd.DataFrame
            Index = symbol, columns = [ltp, change_pct].
            Symbols that fail are filled with NaN.
        """
        payload = {"symbols": ",".join(symbols)}
        response = self._fyers.quotes(payload)

        if response.get("s") != "ok":
            log.warning("Quotes API error: %s", response)
            return pd.DataFrame(index=symbols, columns=["ltp", "change_pct"])

        rows = {}
        for item in response.get("d", []):
            v = item.get("v", {})
            sym = item.get("n", "")
            rows[sym] = {
                "ltp": v.get("lp"),
                "change_pct": v.get("chp"),
            }

        df = pd.DataFrame(rows).T.reindex(symbols)
        df.index.name = "symbol"
        return df.astype(float)

    def get_history_multi(
        self,
        symbols: list[str],
        resolution: str,
        sleep_sec: float = config.API_SLEEP_SECONDS,
        **kwargs,
    ) -> dict[str, pd.DataFrame]:
        """
        Fetch history for multiple symbols, sleeping *sleep_sec* seconds between
        calls to stay inside Fyers rate limits.

        Returns ``{symbol: DataFrame}``.  Symbols that error get an empty DataFrame.
        """
        results: dict[str, pd.DataFrame] = {}
        for i, symbol in enumerate(symbols):
            try:
                results[symbol] = self.get_history(symbol, resolution, **kwargs)
            except RuntimeError as exc:
                log.error("Skipping %s: %s", symbol, exc)
                results[symbol] = pd.DataFrame()
            if i < len(symbols) - 1:
                time.sleep(sleep_sec)
        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_timestamps(df: pd.DataFrame, resolution: str) -> pd.DataFrame:
        """Convert epoch-second timestamps → IST-localised DatetimeIndex."""
        dt = pd.to_datetime(df["datetime"], unit="s", utc=True).dt.tz_convert(
            "Asia/Kolkata"
        )
        if resolution in ("D", "W", "M"):
            df["datetime"] = pd.to_datetime(dt.dt.date)
        else:
            df["datetime"] = dt.dt.tz_localize(None)
        return df
