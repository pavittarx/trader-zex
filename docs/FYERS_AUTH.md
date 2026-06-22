# Fyers Authentication

This project supports **two** authentication flows for Fyers API:

1. **Interactive login** (for development) — browser-based OAuth
2. **Headless login** (for production/sandbox) — TOTP 2FA, no browser needed

---

## Quick Start

### Interactive Login (Development)

```bash
uv run poe auth
```

**Flow:**
1. CLI prints a Fyers login URL
2. You open the URL in a browser and log in
3. You're redirected; copy the `auth_code` from the URL
4. Paste it back into the CLI
5. Access token is saved to `~/.fyers_token.json`
6. Token is cached for the day; next run reuses it

**Use this for:** Local development, testing, one-off runs.

---

### Headless Login (Production/Sandbox/EC2)

Requires **three credentials** in your `.env` file:

```bash
FYERS_FY_ID=<your-fyers-id>           # Login ID (e.g., XB1234)
FYERS_PIN=<4-digit-pin>               # Trading PIN
FYERS_TOTP_SECRET=<base32-secret>     # 2FA seed (from Fyers auth app setup)
```

**How to obtain these:**

1. **FYERS_FY_ID**: Your Fyers login ID (username), shown on your account settings.

2. **FYERS_PIN**: Your 4-digit trading PIN used for order placement.

3. **FYERS_TOTP_SECRET**: The base32-encoded 2FA seed:
   - Log in to Fyers web → Settings → Security → Enable 2FA authenticator
   - When prompted to scan QR code, instead click "Can't scan?" or "Enter code manually"
   - Copy the base32 seed (e.g., `JBSWY3DPEBLW64TMMQQQ====`)
   - Save this in `.env` as `FYERS_TOTP_SECRET=<seed>`

**Once configured, run:**

```bash
uv run poe auth
```

**Flow (automatic, no browser):**
1. CLI sends OTP request
2. CLI generates TOTP from your secret (valid for 30 sec window)
3. CLI verifies PIN with Fyers backend
4. CLI fetches auth code (same as browser redirect)
5. CLI exchanges code for access token
6. Token cached to `~/.fyers_token.json`

**Use this for:** Production servers, EC2 sandbox nodes, any CI/CD, scheduled refreshes.

---

## Token Caching

- Tokens are saved to `~/.fyers_token.json` with today's date
- Same token is reused for all Fyers API calls **on the same day**
- Token refreshes automatically at midnight (next day)
- Both interactive and headless flows cache the same way

---

## Fallback Chain

The `login()` function tries:

1. **Check cache** — if today's token exists, use it
2. **Headless** — if `FYERS_FY_ID`, `FYERS_PIN`, `FYERS_TOTP_SECRET` are set, try headless flow
3. **Interactive** — if headless fails or creds missing, fall back to browser

This means:
- On **EC2/sandbox** with env vars set, tokens refresh unattended
- On **local dev** without TOTP creds, it gracefully falls back to browser login
- Backtest runs with no secrets always use cache or interactive

---

## Security Notes

⚠️ **SENSITIVE**: `FYERS_TOTP_SECRET` + `FYERS_PIN` = full account access.

- **Never** commit `.env` to git — add to `.gitignore`
- Store `.env` only on the machine (or inject via Docker/EC2 secrets manager)
- In production: use IAM roles, Secrets Manager, or similar
- Example secure setup:

```bash
# On your EC2 instance (e.g., via user-data or SecureString param)
export FYERS_CLIENT_ID="ABCD1234-100"
export FYERS_SECRET_KEY="secret_key_here"
export FYERS_FY_ID="XB1234"
export FYERS_PIN="1234"
export FYERS_TOTP_SECRET="JBSWY3DPEBLW64TMMQQQ===="

# Or read from AWS Secrets Manager:
python -c "import boto3; sm=boto3.client('secretsmanager'); s=sm.get_secret_value(SecretId='trader-zex-fyers')['SecretString']; os.environ.update(json.loads(s))"
```

---

## Troubleshooting

### "Headless login failed: verify_otp failed"

**Cause:** TOTP seed is wrong or your device time is out of sync.

**Fix:**
- Double-check `FYERS_TOTP_SECRET` is copied correctly (base32, case-sensitive)
- Sync your device time: `ntpdate -s time.nist.gov` (Linux) or Settings → Date & Time (Mac/Windows)
- Try interactive login to re-authenticate

### "Headless login failed: verify_pin failed"

**Cause:** `FYERS_PIN` is incorrect.

**Fix:**
- Verify your 4-digit trading PIN (not password)
- If you've reset it recently, allow a few minutes for Fyers backend to sync

### "Token generation failed"

**Cause:** Invalid `FYERS_CLIENT_ID` or `FYERS_SECRET_KEY`.

**Fix:**
- Log into Fyers Develop → My Apps
- Copy your app's Client ID and Secret Key exactly
- Paste into `.env`

### Auth works locally but fails on EC2/sandbox

**Cause:** Missing env vars on the remote machine.

**Fix:**
- SSH into the instance and verify `echo $FYERS_FY_ID` (etc) are set
- Restart the process after setting env vars
- Check `/etc/environment` or systemd service file for permanent exports

---

## API Reference

### `core.brokers.fyers.auth`

```python
from core.brokers.fyers.auth import login, interactive_login, headless_login, load_token

# Recommended: use login() — it tries all flows automatically
token = login()  # cached → headless → interactive

# Or explicit:
token = interactive_login()  # browser-based, single-factor
token = headless_login()     # TOTP 2FA, no browser
token = load_token()         # None if no cache or expired
```

---

## Automation Example

**Cron job to refresh token daily at 03:30 AM IST:**

```bash
# In crontab -e
30 03 * * * cd /home/trader/trader-zex && /usr/bin/uv run poe auth >> /var/log/trader-zex-auth.log 2>&1
```

**Or in systemd timer (recommended):**

```ini
# /etc/systemd/system/trader-zex-auth.service
[Unit]
Description=Trader Zex Fyers Auth Refresh
After=network.target

[Service]
Type=oneshot
User=trader
WorkingDirectory=/home/trader/trader-zex
ExecStart=/usr/bin/uv run poe auth
Environment="PATH=/home/trader/.cargo/bin:/usr/bin"

# /etc/systemd/system/trader-zex-auth.timer
[Unit]
Description=Run Trader Zex auth daily
Requires=trader-zex-auth.service

[Timer]
OnCalendar=*-*-* 03:30:00 IST
Persistent=true

[Install]
WantedBy=timers.target

# Enable: systemctl enable --now trader-zex-auth.timer
```

---

## See Also

- `core/brokers/fyers/client.py` — low-level Fyers API wrapper
- `core/brokers/fyers/adapter.py` — broker-agnostic DataAdapter + ExecutionAdapter
- `.env.example` — template for all credentials
