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

from core import config

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


# ---------------------------------------------------------------------------
# Headless (TOTP) login — unattended daily token refresh, no browser
# ---------------------------------------------------------------------------

# Fyers' internal login API (not the public SDK). Replays the browser login:
# send OTP → verify TOTP → verify PIN → fetch auth_code. May change upstream.
_VAGATOR = "https://api-t2.fyers.in/vagator/v2"
_TOKEN_URL = "https://api-t1.fyers.in/api/v3/token"


def headless_login() -> str:
    """Mint a fresh access token with no browser, using TOTP 2FA.

    Requires FYERS_FY_ID, FYERS_PIN, FYERS_TOTP_SECRET in the environment.
    Steps: send_login_otp → verify_otp(TOTP) → verify_pin → token(auth_code)
    → exchange auth_code for the daily access_token (reuses generate_token).
    """
    import base64
    from urllib.parse import urlparse, parse_qs

    import pyotp
    import requests

    fy_id, pin, secret = config.FYERS_FY_ID, config.FYERS_PIN, config.FYERS_TOTP_SECRET
    if not (fy_id and pin and secret):
        raise RuntimeError("headless_login needs FYERS_FY_ID, FYERS_PIN, FYERS_TOTP_SECRET")

    def b64(v: str) -> str:
        return base64.b64encode(str(v).encode()).decode()

    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})

    # 1) send login OTP → request_key
    r1 = s.post(f"{_VAGATOR}/send_login_otp_v2",
                json={"fy_id": b64(fy_id), "app_id": "2"}, timeout=20).json()
    rk = r1.get("request_key")
    if not rk:
        raise RuntimeError(f"send_login_otp failed: {r1}")

    # 2) verify TOTP (retry once in case we straddled the 30s code boundary)
    rk2 = None
    for _ in range(2):
        r2 = s.post(f"{_VAGATOR}/verify_otp",
                    json={"request_key": rk, "otp": pyotp.TOTP(secret).now()}, timeout=20).json()
        rk2 = r2.get("request_key")
        if rk2:
            break
    if not rk2:
        raise RuntimeError(f"verify_otp failed: {r2}")

    # 3) verify PIN → vagator access token
    r3 = s.post(f"{_VAGATOR}/verify_pin_v2",
                json={"request_key": rk2, "identity_type": "pin", "identifier": b64(pin)},
                timeout=20).json()
    vagator_token = (r3.get("data") or {}).get("access_token")
    if not vagator_token:
        raise RuntimeError(f"verify_pin failed: {r3}")

    # 4) fetch the auth_code (same artifact the browser redirect yields)
    app_id, _, app_type = config.FYERS_CLIENT_ID.partition("-")   # "ABCD1234", "100"
    r4 = s.post(_TOKEN_URL,
                headers={"authorization": f"Bearer {vagator_token}"},
                json={"fyers_id": fy_id, "app_id": app_id, "redirect_uri": config.FYERS_REDIRECT_URI,
                      "appType": app_type, "code_challenge": "", "state": "trader_zex",
                      "scope": "", "nonce": "", "response_type": "code", "create_cookie": True},
                timeout=20).json()
    url = r4.get("Url") or r4.get("url")
    auth_code = parse_qs(urlparse(url).query).get("auth_code", [None])[0] if url else None
    if not auth_code:
        raise RuntimeError(f"auth_code step failed: {r4}")

    # 5) exchange auth_code → access_token (persists via _save_token)
    token = generate_token(auth_code)
    log.info("Headless login succeeded; token refreshed.")
    return token


def login() -> str:
    """Return a valid access token: cached → headless (if creds) → interactive."""
    token = load_token()
    if token:
        return token
    if config.FYERS_FY_ID and config.FYERS_PIN and config.FYERS_TOTP_SECRET:
        try:
            return headless_login()
        except Exception as exc:
            log.warning("Headless login failed (%s); falling back to interactive.", exc)
    return interactive_login()


if __name__ == "__main__":
    login()
