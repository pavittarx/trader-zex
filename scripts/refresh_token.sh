#!/bin/zsh
# Daily Fyers token refresh (launchd: com.trader-zex.fyers-auth, 08:45 IST).
# login(): cached -> headless TOTP -> interactive. Headless needs the
# FYERS_FY_ID / FYERS_PIN / FYERS_TOTP_SECRET vars in .env.
# On failure: log + macOS notification (a silent miss would stall every
# unattended run that day — see strategies/pead/STATUS.md milestone 1).
set -u
cd "$(dirname "$0")/.."
LOG=~/.trader_zex/auth_refresh.log
mkdir -p ~/.trader_zex

{
  echo "--- $(date '+%Y-%m-%d %H:%M:%S %Z') ---"
  if /Users/pavix/.local/bin/uv run python -c "
import sys
from core.brokers.fyers.auth import load_token, headless_login
if load_token():
    print('token still valid — nothing to do')
    sys.exit(0)
headless_login()
print('token refreshed (headless)')
"; then
    echo "OK"
  else
    echo "FAILED (exit $?)"
    osascript -e 'display notification "Fyers token refresh FAILED — run: uv run poe auth" with title "trader-zex" sound name "Basso"'
  fi
} >> "$LOG" 2>&1
