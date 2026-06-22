"""Lightweight, self-contained strategy config template.

Each strategy reads from environment variables (stored in ~/.env or injected at runtime)
and provides all runtime parameters. The same config powers backtest, paper-trade,
sandbox, and live deployments.

Secrets (API keys, broker tokens) are loaded from environment; they never appear
in code or git. See .env.example for required variables.

Usage
-----
    # Backtest (no secrets needed)
    uv run python -m strategies.<name>.backtest

    # Paper/Sandbox/Live (secrets from ~/.env or passed via -e in docker/EC2)
    export FYERS_FY_ID="..." FYERS_PIN="..." FYERS_TOTP_SECRET="..."
    uv run python -m runners.sandbox <name>

Environment variables
---------------------
Inherited from core/config.py (set once, shared by all strategies):
  FYERS_FY_ID, FYERS_PIN, FYERS_TOTP_SECRET (Fyers auth)
  BACKTEST_INITIAL_CAPITAL (default 100000 INR)

Strategy-specific (<name>):
  <NAME>_PAPER_TRADE_SIZE_PCT: 10–100 (default: 100 for backtest, 10% for shadow)
  <NAME>_LOG_DIR: path to write daily P&L logs (default: ~/.trader_zex/logs/<name>/)
"""
from __future__ import annotations

import os
from pathlib import Path

from core import config as core_config
from strategies._template.manifest import MANIFEST

_P = MANIFEST.params


class StrategyConfig:
    """Runtime config for strategy across all stages (backtest→paper→sandbox→live)."""

    def __init__(self, strategy_name: str = "template"):
        """Load config from manifest + environment.

        Parameters
        ----------
        strategy_name : str
            Name of strategy (for env var prefix, e.g. "momentum" → MOMENTUM_* vars)
        """
        self.name = strategy_name
        prefix = strategy_name.upper()

        # Core params (immutable, from manifest)
        for key, val in _P.items():
            setattr(self, key, val)

        # Runtime (from environment or defaults)
        self.paper_trade_size_pct = float(
            os.getenv(f"{prefix}_PAPER_TRADE_SIZE_PCT", "100")
        )
        self.log_dir = Path(
            os.getenv(f"{prefix}_LOG_DIR", f"~/.trader_zex/logs/{strategy_name}/")
        ).expanduser()
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Broker config (inherited from core)
        self.broker = MANIFEST.broker
        self.initial_capital = core_config.BACKTEST_INITIAL_CAPITAL

    def __repr__(self) -> str:
        params_str = ", ".join(f"{k}={v}" for k, v in _P.items())
        return f"{self.name.title()}Config({params_str})"
