# EC2 Deployment Guide (Trader Zex + Parseable UI Logs)

This guide is an operator runbook you can hand to a coding model (or execute
yourself) to deploy Trader Zex on EC2 and view structured logs in Parseable UI.

## 1) Provision EC2

- **OS:** Ubuntu 22.04 LTS
- **Instance:** `t3.large` minimum (strategy + data + logging)
- **Storage:** 80+ GB gp3
- **Security group inbound:**
  - `22` (SSH) from your IP
  - `8000` (Parseable UI/API) from your IP/VPN only
- **Timezone:** keep server in UTC; schedule with explicit IST conversion

## 2) Base setup on EC2

```bash
sudo apt-get update
sudo apt-get install -y git curl ca-certificates build-essential jq python3-pip docker.io
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
# re-login once so docker group membership applies

# uv installer
curl -LsSf https://astral.sh/uv/install.sh | sh
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

mkdir -p ~/apps && cd ~/apps
git clone https://github.com/pavittarx/trader-zex.git
cd trader-zex
uv sync
```

## 3) Secrets and runtime directories

Create `~/.env`:

```bash
cat > ~/.env << 'EOF'
# Fyers app creds
FYERS_CLIENT_ID=...
FYERS_SECRET_KEY=...
FYERS_REDIRECT_URI=https://trade.fyers.in/api-login/redirect-uri/index.html

# Fyers account creds (headless auth)
FYERS_FY_ID=...
FYERS_PIN=...
FYERS_TOTP_SECRET=...

# Optional strategy/runtime config
BACKTEST_INITIAL_CAPITAL=100000
MOMENTUM_PAPER_TRADE_SIZE_PCT=100

# Parseable sink (used by shared sandbox observer)
PARSEABLE_URL=http://127.0.0.1:8000
PARSEABLE_USERNAME=admin
PARSEABLE_PASSWORD=admin
PARSEABLE_STREAM=trader_zex_sandbox
PARSEABLE_VERIFY_TLS=false
EOF

chmod 600 ~/.env
mkdir -p ~/.trader_zex/logs ~/.trader_zex/state ~/.trader_zex/cache
```

## 4) Start Parseable (UI + ingest API)

```bash
sudo mkdir -p /var/lib/parseable/data /var/lib/parseable/staging
sudo chown -R $USER:$USER /var/lib/parseable

docker run -d --name parseable \
  -p 8000:8000 -p 8001:8001 -p 8002:8002 \
  -v /var/lib/parseable/data:/parseable/data \
  -v /var/lib/parseable/staging:/parseable/staging \
  -e P_FS_DIR=/parseable/data \
  -e P_STAGING_DIR=/parseable/staging \
  quay.io/parseablehq/parseable:latest \
  parseable local-store
```

Open `http://<EC2_PUBLIC_IP>:8000` and login with `admin/admin` (change creds in
Parseable config after first setup).

## 5) Validate Parseable ingest endpoint

```bash
curl --location --request POST 'http://127.0.0.1:8000/api/v1/ingest' \
  --header 'X-P-Stream: trader_zex_sandbox' \
  --header 'Authorization: Basic YWRtaW46YWRtaW4=' \
  --header 'Content-Type: application/json' \
  --data-raw '[{"kind":"smoke_test","source":"ec2","ts":"2026-01-01T00:00:00Z"}]'
```

Then in Parseable UI, open stream `trader_zex_sandbox` and confirm the record.

## 6) Prime Fyers token (headless)

```bash
cd ~/apps/trader-zex
set -a && source ~/.env && set +a
uv run poe auth
```

This creates `~/.fyers_token.json`. If headless auth fails, fix `FYERS_*`
variables before proceeding.

## 7) Create systemd services

Create a reusable environment file for systemd:

```bash
cat > ~/apps/trader-zex/.env.runtime << 'EOF'
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/home/ubuntu/.local/bin
HOME=/home/ubuntu
EOF
```

### 7.1 Daily auth refresh service + timer

```bash
sudo tee /etc/systemd/system/trader-zex-auth.service > /dev/null << 'EOF'
[Unit]
Description=Trader Zex Fyers token refresh
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=ubuntu
WorkingDirectory=/home/ubuntu/apps/trader-zex
EnvironmentFile=/home/ubuntu/apps/trader-zex/.env.runtime
ExecStart=/bin/bash -lc 'set -a && source /home/ubuntu/.env && set +a && uv run poe auth'
EOF

sudo tee /etc/systemd/system/trader-zex-auth.timer > /dev/null << 'EOF'
[Unit]
Description=Run Trader Zex auth refresh daily (IST)

[Timer]
OnCalendar=*-*-* 03:30:00 Asia/Kolkata
Persistent=true

[Install]
WantedBy=timers.target
EOF
```

### 7.2 Weekly momentum paper rebalance service + timer

Use paper until the strategy is promoted to sandbox/live.

```bash
sudo tee /etc/systemd/system/trader-zex-momentum-paper.service > /dev/null << 'EOF'
[Unit]
Description=Trader Zex momentum weekly paper cycle
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=ubuntu
WorkingDirectory=/home/ubuntu/apps/trader-zex
EnvironmentFile=/home/ubuntu/apps/trader-zex/.env.runtime
ExecStart=/bin/bash -lc 'set -a && source /home/ubuntu/.env && set +a && uv run python -m runners.paper momentum --n-symbols 100 --lookback-days 900'
EOF

sudo tee /etc/systemd/system/trader-zex-momentum-paper.timer > /dev/null << 'EOF'
[Unit]
Description=Run momentum paper weekly (Friday 15:30 IST)

[Timer]
OnCalendar=Fri *-*-* 15:30:00 Asia/Kolkata
Persistent=true

[Install]
WantedBy=timers.target
EOF
```

### 7.3 Optional PEAD sandbox daily service + timer

Use this only while `pead` is at `sandbox` stage.

```bash
sudo tee /etc/systemd/system/trader-zex-pead-sandbox.service > /dev/null << 'EOF'
[Unit]
Description=Trader Zex PEAD sandbox cycle
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=ubuntu
WorkingDirectory=/home/ubuntu/apps/trader-zex
EnvironmentFile=/home/ubuntu/apps/trader-zex/.env.runtime
ExecStart=/bin/bash -lc 'set -a && source /home/ubuntu/.env && set +a && uv run python -m runners.sandbox pead'
EOF

sudo tee /etc/systemd/system/trader-zex-pead-sandbox.timer > /dev/null << 'EOF'
[Unit]
Description=Run PEAD sandbox daily (EOD)

[Timer]
OnCalendar=Mon..Fri *-*-* 15:45:00 Asia/Kolkata
Persistent=true

[Install]
WantedBy=timers.target
EOF
```

Enable timers:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now trader-zex-auth.timer
sudo systemctl enable --now trader-zex-momentum-paper.timer
# optional
sudo systemctl enable --now trader-zex-pead-sandbox.timer
```

## 8) Manual trigger and health checks

```bash
# Trigger now
sudo systemctl start trader-zex-auth.service
sudo systemctl start trader-zex-momentum-paper.service

# Timer/service status
systemctl list-timers --all | grep trader-zex
systemctl status trader-zex-momentum-paper.service --no-pager
```

## 9) Where logs go

- **Systemd stdout/stderr**
  - `journalctl -u trader-zex-momentum-paper.service -n 200 --no-pager`
  - `journalctl -u trader-zex-pead-sandbox.service -n 200 --no-pager`
- **Shared structured observer (JSONL fallback)**
  - `~/.trader_zex/logs/sandbox/shared_session.jsonl`
- **Strategy logs/state**
  - `~/.trader_zex/logs/`
  - `~/.trader_zex/state/`

## 10) Parseable UI usage (log visibility)

1. Open `http://<EC2_PUBLIC_IP>:8000`.
2. Select stream `trader_zex_sandbox`.
3. Filter by `kind` values:
   - `market_client_started`
   - `shared_session_started`
   - `sandbox_heartbeat`
   - `sandbox_fill`
   - `strategy_cycle`
4. Save a query/view for:
   - latest strategy cycles
   - fill events
   - heartbeat continuity

## 11) Minimal rollback and recovery

```bash
# Stop automation only
sudo systemctl disable --now trader-zex-momentum-paper.timer
sudo systemctl disable --now trader-zex-pead-sandbox.timer

# Keep auth timer if needed
sudo systemctl status trader-zex-auth.timer --no-pager
```

If Parseable is down, Trader Zex keeps local JSONL logs and resumes remote
delivery when Parseable is back.
