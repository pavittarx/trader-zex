"""DataAdapter implementation over the existing FyersClient."""
from __future__ import annotations

from datetime import date, tzinfo
from zoneinfo import ZoneInfo

import pandas as pd

from core.brokers.base import DataAdapter
from core.brokers.fyers.client import FyersClient, resample_ohlcv

_IST = ZoneInfo("Asia/Kolkata")


class FyersDataAdapter(DataAdapter):
    """Fyers API v3 — NSE equities. Timestamps are IST-naive."""

    def __init__(self, access_token: str | None = None,
                 client: FyersClient | None = None):
        self._client = client or FyersClient(access_token=access_token)

    @property
    def venue(self) -> str:
        return "NSE"

    @property
    def tz(self) -> tzinfo:
        return _IST

    def to_symbol(self, ticker: str) -> str:
        return ticker if ticker.startswith("NSE:") else f"NSE:{ticker}"

    def to_ticker(self, symbol: str) -> str:
        return symbol.removeprefix("NSE:")

    def get_history(self, symbol: str, resolution: str, *,
                    date_from: date | None = None,
                    date_to: date | None = None) -> pd.DataFrame:
        return self._client.get_history(symbol, resolution,
                                        date_from=date_from, date_to=date_to)

    def get_history_multi(self, symbols: list[str], resolution: str,
                          **kwargs) -> dict[str, pd.DataFrame]:
        return self._client.get_history_multi(symbols, resolution, **kwargs)

    def get_quotes(self, symbols: list[str]) -> pd.DataFrame:
        return self._client.get_quotes(symbols)

    @staticmethod
    def resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
        return resample_ohlcv(df, rule)
