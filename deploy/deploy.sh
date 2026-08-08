#!/bin/bash
set -e

APP_DIR="/opt/monitoring-hub"
REPO_DIR="$APP_DIR/app"
VENV_DIR="$APP_DIR/venv"
SERVICE_NAME="monitoring-hub"

echo "=== Deploying ASLOps Monitoring Hub ==="

# ── Pull latest code ─────────────────────────────────────────
if [ -d "$REPO_DIR" ]; then
    echo "--- Pulling latest code ---"
    cd "$REPO_DIR"
    git pull origin main
else
    echo "--- Cloning repo ---"
    git clone https://github.com/vinayhirap/Monitoring-Hub-V1.git "$REPO_DIR"
    cd "$REPO_DIR"
fi

# ── Python venv + dependencies ───────────────────────────────
echo "--- Setting up Python environment ---"
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install -r requirements.txt

# ── Environment file ─────────────────────────────────────────
echo "--- Copying .env ---"
cp "$APP_DIR/.env.production" "$REPO_DIR/.env"

# ── Import DB (only if tables missing) ──────────────────────
TABLE_COUNT=$(mysql -umonitor -proot123 monitoring_hub -e "SHOW TABLES;" 2>/dev/null | wc -l)
if [ "$TABLE_COUNT" -lt 2 ]; then
    echo "--- Importing database schema ---"
    mysql -umonitor -proot123 monitoring_hub < "$REPO_DIR/db/monitoring_hub_dump.sql"
    echo "--- DB imported ---"
else
    echo "--- DB already has tables, skipping import ---"
fi

# ── Build frontend ───────────────────────────────────────────
echo "--- Building frontend ---"
cd "$REPO_DIR/frontend"
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - 2>/dev/null || true
sudo apt install -y nodejs 2>/dev/null || true
npm install
npm run build

# ── Systemd service ──────────────────────────────────────────
echo "--- Configuring systemd service ---"
sudo tee /etc/systemd/system/monitoring-hub.service > /dev/null <<EOF
[Unit]
Description=ASLOps Monitoring Hub
After=network.target mysql.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$REPO_DIR
Environment="PATH=$VENV_DIR/bin"
EnvironmentFile=$REPO_DIR/.env
ExecStart=$VENV_DIR/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable monitoring-hub
sudo systemctl restart monitoring-hub

echo "--- Service status ---"
sudo systemctl status monitoring-hub --no-pager

echo "=== Deploy complete ==="
