"""Lightweight, self-contained PEAD strategy config.

This config reads from environment variables (stored in ~/.env or injected at runtime)
and provides all runtime parameters. The same config powers backtest, paper-trade,
sandbox, and live deployments.

Secrets (API keys, broker tokens) are loaded from environment; they never appear
in code or git. See .env.example for required variables.

Usage
-----
    # Backtest (no secrets needed)
    uv run python -m strategies.pead.backtest

    # Paper/Sandbox/Live (secrets from ~/.env or passed via -e in docker/EC2)
    export FYERS_FY_ID="..." FYERS_PIN="..." FYERS_TOTP_SECRET="..."
    uv run python -m runners.sandbox pead

Environment variables
---------------------
Inherited from core/config.py (set once, shared by all strategies):
  FYERS_FY_ID, FYERS_PIN, FYERS_TOTP_SECRET (Fyers auth)
  BACKTEST_INITIAL_CAPITAL (default 100000 INR)

Strategy-specific (PEAD):
  PEAD_PAPER_TRADE_SIZE_PCT: 10–100 (default: 100 for paper, 10% for shadow)
  PEAD_LOG_DIR: path to write daily P&L + reaction logs (default: ~/.trader_zex/logs/pead/)
"""
from __future__ import annotations

import os
from pathlib import Path

from core import config as core_config
from strategies.pead.manifest import MANIFEST

_P = MANIFEST.params


class PEADConfig:
    """Runtime config for PEAD strategy across all stages (backtest→paper→sandbox→live)."""

    def __init__(self):
        """Load config from manifest + environment."""
        # Core params (immutable, from manifest)
        self.hold_bars = _P["hold_bars"]
        self.thresh = _P["thresh"]
        self.stop_pct = _P["stop_pct"]
        self.corp_gap = _P["corp_gap"]
        self.alloc_pct = _P["alloc_pct"]
        self.max_gross = _P["max_gross"]
        self.leg_bps = _P["leg_bps"]

        # Universe (locked, from manifest)
        self.universe = MANIFEST.universe

        # Runtime (from environment or defaults)
        self.paper_trade_size_pct = float(os.getenv("PEAD_PAPER_TRADE_SIZE_PCT", "100"))
        self.log_dir = Path(os.getenv("PEAD_LOG_DIR", "~/.trader_zex/logs/pead/")).expanduser()
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Broker config (inherited from core)
        self.broker = MANIFEST.broker  # "fyers"
        self.initial_capital = core_config.BACKTEST_INITIAL_CAPITAL

    def cost_model(self) -> dict:
        """Return cost breakdown (bps per round-trip).

        PEAD trades: entry at reaction close + exit at +20 session close.
        Entry cost: STT (5 bps) + exchange (5 bps) + half-spread (10 bps) = 20 bps
        Exit cost: same = 20 bps
        Total round-trip: ~40 bps
        """
        return {
            "entry_bps": self.leg_bps,
            "exit_bps": self.leg_bps,
            "round_trip_bps": 2 * self.leg_bps,
        }

    def __repr__(self) -> str:
        return (
            f"PEADConfig(\n"
            f"  hold_bars={self.hold_bars}, thresh={self.thresh*100:.1f}%, "
            f"alloc={self.alloc_pct*100:.0f}%,\n"
            f"  universe={len(self.universe)} names, paper_size={self.paper_trade_size_pct}%\n"
            f")"
        )
