"""Broker adapter interfaces.

DataAdapter is sized to what the codebase actually calls today (screener,
ranker, research scripts, backtest data_loader): history, quotes, resample,
plus the venue/timezone/symbol-format facts that were previously implicit
Fyers assumptions scattered through the code.

ExecutionAdapter is the live-only seam: it produces the NautilusTrader
client configs for a TradingNode. Backtests never touch it, and sandbox
needs only the data side (NT's SandboxExecutionClient fakes the fills).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, tzinfo

import pandas as pd


class DataAdapter(ABC):
    """Historical + snapshot market data for one broker/venue."""

    @property
    @abstractmethod
    def venue(self) -> str:
        """Venue code, e.g. 'NSE'. Used in cache keys and NT instrument IDs."""

    @property
    @abstractmethod
    def tz(self) -> tzinfo:
        """Exchange timezone of the timestamps get_history returns (naive)."""

    @abstractmethod
    def to_symbol(self, ticker: str) -> str:
        """Broker symbol from a plain ticker: 'RELIANCE-EQ' -> 'NSE:RELIANCE-EQ'."""

    @abstractmethod
    def to_ticker(self, symbol: str) -> str:
        """Inverse of to_symbol."""

    @abstractmethod
    def get_history(self, symbol: str, resolution: str, *,
                    date_from: date | None = None,
                    date_to: date | None = None) -> pd.DataFrame:
        """OHLCV DataFrame indexed by exchange-tz-naive timestamps."""

    @abstractmethod
    def get_history_multi(self, symbols: list[str], resolution: str,
                          **kwargs) -> dict[str, pd.DataFrame]: ...

    @abstractmethod
    def get_quotes(self, symbols: list[str]) -> pd.DataFrame: ...

    @staticmethod
    @abstractmethod
    def resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
        """Resample an OHLCV frame to a coarser broker-native resolution."""


class ExecutionAdapter(ABC):
    """Live-trading seam: NautilusTrader client configs for a TradingNode."""

    @abstractmethod
    def make_nt_data_client_config(self): ...

    @abstractmethod
    def make_nt_exec_client_config(self): ...
