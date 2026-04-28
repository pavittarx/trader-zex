"""
Fyers API v3 authentication helpers.

Flow:
  1. build_auth_url()   → open in browser, user logs in, copies the auth-code
                          from the redirect URL's ?auth_code= query param.
  2. generate_token(auth_code) → exchanges code for access_token, persists it.
  3. load_token()       → returns a stored token or None if absent/expired.
"""

import json
import logging
from datetime import date, datetime
from pathlib import Path

from fyers_apiv3 import fyersModel

import config

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Token persistence
# ---------------------------------------------------------------------------

def _token_path() -> Path:
    return config.TOKEN_FILE


def _save_token(access_token: str) -> None:
    payload = {
        "access_token": access_token,
        "saved_date": date.today().isoformat(),
    }
    path = _token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))
    log.info("Token saved to %s", path)


def load_token() -> str | None:
    """Return today's token if one was persisted, else None."""
    path = _token_path()
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
        if payload.get("saved_date") == date.today().isoformat():
            return payload["access_token"]
    except (json.JSONDecodeError, KeyError):
        pass
    return None


# ---------------------------------------------------------------------------
# Auth-code flow
# ---------------------------------------------------------------------------

def build_auth_url() -> str:
    """Return the Fyers login URL the user must visit to obtain an auth code."""
    session = fyersModel.SessionModel(
        client_id=config.FYERS_CLIENT_ID,
        secret_key=config.FYERS_SECRET_KEY,
        redirect_uri=config.FYERS_REDIRECT_URI,
        response_type="code",
        grant_type="authorization_code",
    )
    return session.generate_authcode()


def generate_token(auth_code: str) -> str:
    """Exchange *auth_code* for an access token, persist it, and return it."""
    session = fyersModel.SessionModel(
        client_id=config.FYERS_CLIENT_ID,
        secret_key=config.FYERS_SECRET_KEY,
        redirect_uri=config.FYERS_REDIRECT_URI,
        response_type="code",
        grant_type="authorization_code",
    )
    session.set_token(auth_code)
    response = session.generate_token()

    if response.get("s") != "ok":
        raise RuntimeError(f"Token generation failed: {response}")

    access_token = response["access_token"]
    _save_token(access_token)
    return access_token


# ---------------------------------------------------------------------------
# Interactive helper
# ---------------------------------------------------------------------------

def interactive_login() -> str:
    """
    Console-based login:
      - Checks for a valid cached token first.
      - If none, prints the auth URL, waits for the user to paste the auth code.
    Returns the access token.
    """
    token = load_token()
    if token:
        log.info("Loaded cached token from %s", _token_path())
        return token

    url = build_auth_url()
    print("\n--- Fyers Authentication ---")
    print("Open the following URL in your browser and log in:")
    print(f"\n  {url}\n")
    print("After login you will be redirected.  Copy the 'auth_code' value")
    print("from the redirect URL (looks like: ?auth_code=xxxxxxxx&...)\n")
    auth_code = input("Paste auth_code here: ").strip()

    token = generate_token(auth_code)
    print("Authentication successful.\n")
    return token
