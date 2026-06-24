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

### 7.2 Strategy trading — a long-running NT `TradingNode` service

> **Architecture rule: trading runs as a NautilusTrader `TradingNode`, never a
> cron/timer batch.** Sandbox and live are the *same* NT node (only the execution
> client differs), so what you forward-test is what you trade — see
> [ENVIRONMENTS.md](ENVIRONMENTS.md). The node owns market-hours scheduling and
> bar-event timing **internally**; no systemd timer decides when to trade. The
> only timer on the box is the infra auth refresh in §7.1.
>
> **⚠️ BLOCKED — not runnable yet.** The Fyers NT `DataClient` + sandbox/live
> `TradingNode` are **not built** (see the ENVIRONMENTS.md build order). Do **not**
> substitute `runners.paper` / `runners.sandbox` (the `run_paper_cycle` EOD batch)
> here — that path is non-conforming, its fills don't match live, and its output
> is not promotion-grade. There is currently **no conforming way to run a strategy
> unattended on EC2**; the auth timer (§7.1) is the only thing to enable now. When
> the node lands, deploy it with the service template below.

```bash
# TEMPLATE — install only once strategies/<name>/sandbox.py builds a real NT node.
sudo tee /etc/systemd/system/trader-zex-pead.service > /dev/null << 'EOF'
[Unit]
Description=Trader Zex PEAD sandbox TradingNode
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/apps/trader-zex
EnvironmentFile=/home/ubuntu/apps/trader-zex/.env.runtime
# The NT node runs continuously and acts on bar-close events; it does NOT exit
# after one cycle. Restart on crash; the node reconciles state on startup.
ExecStart=/bin/bash -lc 'set -a && source /home/ubuntu/.env && set +a && uv run python -m runners.sandbox pead'
Restart=on-failure
RestartSec=30
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now trader-zex-auth.timer
# trader-zex-pead.service — enable ONLY after the NT node is built:
# sudo systemctl enable --now trader-zex-pead.service
```

If you want the node up only during market hours instead of 24/7, bound it with a
start/stop pair of timers (`OnCalendar=Mon..Fri 09:00 Asia/Kolkata` →
`systemctl start`, `15:45` → `systemctl stop`). That is infra lifecycle, not a
trading reimplementation — the trade decisions still happen inside the NT node.

## 8) Manual trigger and health checks

```bash
# Infra: refresh the token now
sudo systemctl start trader-zex-auth.service

# Timer/service status
systemctl list-timers --all | grep trader-zex
sudo systemctl status trader-zex-pead.service --no-pager   # once the node exists
```

## 9) Where logs go

- **Systemd stdout/stderr** (NT node + auth)
  - `journalctl -u trader-zex-pead.service -n 200 --no-pager`
  - `journalctl -u trader-zex-auth.service -n 200 --no-pager`
- **NT node logs / strategy state**
  - `~/.trader_zex/logs/`
  - `~/.trader_zex/state/` (kill-switch halt state)

## 10) Parseable UI usage (log visibility)

1. Open `http://<EC2_PUBLIC_IP>:8000`.
2. Select the stream the NT node ships to (configure the node's logger/observer
   to POST to Parseable, or ingest journald via a shipper).
3. Save views for order/fill events, position changes, and any kill-switch halt.

> The `kind` values previously listed here (`sandbox_heartbeat`, `sandbox_fill`,
> `strategy_cycle`, …) were emitted by the interim `run_paper_cycle` observer,
> which is non-conforming and slated for removal (see ENVIRONMENTS.md). The NT
> `TradingNode` logs through NT's own logger — wire that to Parseable instead.

## 11) Minimal rollback and recovery

```bash
# Stop the trading node (kill-switch state in ~/.trader_zex/state/ persists;
# open positions run to their in-strategy stop/hold exit)
sudo systemctl disable --now trader-zex-pead.service

# Keep the infra auth timer running
sudo systemctl status trader-zex-auth.timer --no-pager
```

If Parseable is down, Trader Zex keeps local logs and resumes remote delivery
when Parseable is back.
