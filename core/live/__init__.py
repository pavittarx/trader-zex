"""core.live — kill-switch risk machinery and run-state persistence.

Offline-testable foundation for the sandbox/live environments
(docs/ENVIRONMENTS.md). The NT TradingNode wiring (data/exec clients)
lands separately — see strategies/pead/STATUS.md milestones.

Also provides `core.live.fyers_sandbox.get_shared_session()` for sharing a
single Fyers market-data login/session and sandbox execution ledger across
multiple strategies within one process.
"""
