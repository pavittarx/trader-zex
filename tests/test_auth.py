"""Tests for headless (TOTP) auth — the parts testable without live Fyers creds.
The network steps can't be unit-tested offline; we cover the safety guards.
"""
from core import auth


def test_headless_login_requires_credentials(monkeypatch):
    # With creds absent, headless_login must fail fast (before any network call),
    # not silently proceed — this is the safety invariant.
    monkeypatch.setattr(auth.config, "FYERS_FY_ID", "")
    monkeypatch.setattr(auth.config, "FYERS_PIN", "")
    monkeypatch.setattr(auth.config, "FYERS_TOTP_SECRET", "")
    try:
        auth.headless_login()
    except RuntimeError as e:
        assert "FYERS_FY_ID" in str(e)
    else:
        raise AssertionError("headless_login should raise without credentials")


def test_login_uses_cached_token_first(monkeypatch):
    # If a valid cached token exists, login() returns it without any network/auth.
    monkeypatch.setattr(auth, "load_token", lambda: "CACHED_TOKEN")
    assert auth.login() == "CACHED_TOKEN"
