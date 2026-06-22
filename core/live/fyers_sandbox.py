"""Shared Fyers sandbox I/O session.

One process can run multiple strategies while sharing:
- a single market-data client login/session
- a single sandbox execution simulator
"""
from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from core.brokers.fyers.adapter import FyersDataAdapter


class SandboxObserver:
    """Structured observability sink for shared sandbox runtime."""

    def __init__(self, path: Path | None = None):
        self.path = path or Path("~/.trader_zex/logs/sandbox/shared_session.jsonl").expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.parseable_url = os.getenv("PARSEABLE_URL", "").rstrip("/")
        self.parseable_stream = os.getenv("PARSEABLE_STREAM", "trader_zex_sandbox")
        self.parseable_user = os.getenv("PARSEABLE_USERNAME", "")
        self.parseable_pass = os.getenv("PARSEABLE_PASSWORD", "")
        self.parseable_verify_tls = os.getenv("PARSEABLE_VERIFY_TLS", "true").lower() not in {"0", "false", "no"}
        self.parseable_timeout = float(os.getenv("PARSEABLE_TIMEOUT_SEC", "2.5"))
        self.parseable_enabled = bool(self.parseable_url and self.parseable_user and self.parseable_pass)

    def _write(self, payload: dict[str, Any]) -> None:
        row = dict(payload)
        row["ts"] = datetime.utcnow().isoformat()
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        self._emit_parseable(row)

    def _emit_parseable(self, row: dict[str, Any]) -> None:
        if not self.parseable_enabled:
            return
        token = base64.b64encode(f"{self.parseable_user}:{self.parseable_pass}".encode("utf-8")).decode("utf-8")
        headers = {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
            "X-P-Stream": self.parseable_stream,
        }
        try:
            requests.post(
                f"{self.parseable_url}/api/v1/ingest",
                headers=headers,
                json=[row],
                timeout=self.parseable_timeout,
                verify=self.parseable_verify_tls,
            )
        except Exception:
            # Keep local logging as source of truth even if remote sink is down.
            pass

    def event(self, kind: str, **fields: Any) -> None:
        self._write({"kind": kind, **fields})


class LiveMarketDataClient:
    """Thin wrapper over the Fyers adapter for sandbox market reads."""

    def __init__(self, adapter: FyersDataAdapter, observer: SandboxObserver):
        self.adapter = adapter
        self.observer = observer
        # Expose raw FyersClient for call sites that already expect it.
        self.raw_client = adapter._client  # noqa: SLF001
        self.observer.event("market_client_started", venue=self.adapter.venue)

    @property
    def venue(self) -> str:
        return self.adapter.venue


@dataclass
class SandboxExecutionClient:
    """Process-local sandbox execution ledger (no broker orders)."""

    fills: list[dict[str, Any]] = field(default_factory=list)
    observer: SandboxObserver | None = None

    def record_fill(self, strategy: str, symbol: str, side: str, qty: float, price: float) -> None:
        payload = {
            "ts": datetime.utcnow().isoformat(),
            "strategy": strategy,
            "symbol": symbol,
            "side": side,
            "qty": float(qty),
            "price": float(price),
        }
        self.fills.append(payload)
        if self.observer is not None:
            self.observer.event("sandbox_fill", **payload)


@dataclass
class FyersSandboxSession:
    """Shared session object for multi-strategy sandbox runs."""

    market: LiveMarketDataClient
    execution: SandboxExecutionClient
    observer: SandboxObserver

    def emit_heartbeat(self) -> None:
        self.observer.event(
            "sandbox_heartbeat",
            fills_total=len(self.execution.fills),
            venue=self.market.venue,
        )


_SESSION: FyersSandboxSession | None = None


def get_shared_session(require_headless: bool = True) -> FyersSandboxSession:
    """Singleton shared session in current process."""
    global _SESSION
    if _SESSION is None:
        observer = SandboxObserver()
        adapter = FyersDataAdapter(require_headless=require_headless)
        execution = SandboxExecutionClient(observer=observer)
        _SESSION = FyersSandboxSession(
            market=LiveMarketDataClient(adapter, observer=observer),
            execution=execution,
            observer=observer,
        )
        _SESSION.observer.event("shared_session_started", require_headless=require_headless)
    _SESSION.emit_heartbeat()
    return _SESSION
