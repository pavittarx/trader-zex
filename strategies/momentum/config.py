"""Lightweight, self-contained momentum strategy config.

This config reads from environment variables (stored in ~/.env or injected at runtime)
and provides all runtime parameters. The same config powers backtest, paper-trade,
sandbox, and live deployments.

Secrets (API keys, broker tokens) are loaded from environment; they never appear
in code or git. See .env.example for required variables.

Usage
-----
    # Backtest (no secrets needed)
    uv run python -m strategies.momentum.backtest --date-from 2015-01-01 --date-to 2020-12-31

    # Paper/Sandbox/Live (secrets from ~/.env or passed via -e in docker/EC2)
    export FYERS_FY_ID="..." FYERS_PIN="..." FYERS_TOTP_SECRET="..."
    uv run python -m runners.sandbox momentum

Environment variables
---------------------
Inherited from core/config.py (set once, shared by all strategies):
  FYERS_FY_ID, FYERS_PIN, FYERS_TOTP_SECRET (Fyers auth)
  BACKTEST_INITIAL_CAPITAL (default 100000 INR)

Strategy-specific (momentum):
  MOMENTUM_UNIVERSE_SOURCE: "nse-bhavcopy" | "fyers-api" (default: nse-bhavcopy)
  MOMENTUM_PAPER_TRADE_SIZE_PCT: 10–100 (default: 100 for paper, 10% for shadow)
  MOMENTUM_LOG_DIR: path to write daily P&L logs (default: ~/.trader_zex/logs/momentum/)
"""
from __future__ import annotations

import os
from pathlib import Path
from datetime import date

import pandas as pd

from core import config as core_config
from strategies.momentum.manifest import MANIFEST
from strategies.momentum.research.universe_registry import universe_isins_at_date

_P = MANIFEST.params


class MomentumConfig:
    """Runtime config for momentum strategy across all stages (backtest→paper→sandbox→live)."""

    def __init__(self):
        """Load config from manifest + environment."""
        # Core params (immutable, from manifest)
        self.lookback_months = _P["lookback_months"]
        self.ranking_months = _P["ranking_months"]
        self.quintile = _P["quintile"]
        self.rebalance_freq = _P["rebalance_freq"]
        self.turnover_threshold_pct = _P["turnover_threshold_pct"]
        self.max_single_position_pct = _P["max_single_position_pct"]

        # Runtime (from environment or defaults)
        self.universe_source = os.getenv("MOMENTUM_UNIVERSE_SOURCE", "nse-bhavcopy")
        self.paper_trade_size_pct = float(os.getenv("MOMENTUM_PAPER_TRADE_SIZE_PCT", "100"))
        self.log_dir = Path(os.getenv("MOMENTUM_LOG_DIR", "~/.trader_zex/logs/momentum/")).expanduser()
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Broker config (inherited from core)
        self.broker = MANIFEST.broker  # "fyers"
        self.initial_capital = core_config.BACKTEST_INITIAL_CAPITAL

    def universe_nifty500(self, as_of: date | None = None) -> list[str]:
        """Load Nifty 500 constituent ISINs for a given date (or today).

        Returns list of ISINs (e.g. ["INE002A01018", "INE004A01024", ...]).
        Point-in-time: only constituents that were in the index at as_of.
        """
        as_of = as_of or date.today()
        isins = universe_isins_at_date(as_of)
        if not isins:
            raise RuntimeError(
                "No point-in-time universe found in registry. "
                "Initialize/import registry with: "
                "uv run python -m strategies.momentum.research.universe_registry init && "
                "uv run python -m strategies.momentum.research.universe_registry import-csv --csv <path>"
            )
        return isins

    def cost_model(self) -> dict:
        """Return cost breakdown (bps per round-trip).

        Based on NSE retail structure:
          - STT (equity): 0.025% buy + 0.025% sell = 0.05% = 5 bps (both legs)
          - Exchange + clearing: ~10 bps (both legs)
          - Half-spread (est.): ~15 bps (one leg, assume 10 bps typical)
          - Slippage (est.): ~5 bps (one leg)
          Total: ~35 bps conservatively, 50 bps pessimistically

        Strategy uses this to filter out trades below turnover threshold.
        """
        return {
            "stt_bps": 5,              # STT (equity): 5 bps round-trip
            "exchange_bps": 10,        # Exchange + clearing: 10 bps
            "half_spread_bps": 15,     # Bid-ask spread (one leg)
            "slippage_bps": 5,         # Execution slippage
            "round_trip_bps": 35,      # 5 + 10 + (15+5)*2 ≈ 50 bps conservatively
        }

    def __repr__(self) -> str:
        return (
            f"MomentumConfig(\n"
            f"  lookback={self.lookback_months}m, ranking={self.ranking_months}m, "
            f"quintile={self.quintile},\n"
            f"  rebalance={self.rebalance_freq}, turnover_gate={self.turnover_threshold_pct}%,\n"
            f"  universe_source={self.universe_source}, paper_size={self.paper_trade_size_pct}%\n"
            f")"
        )
