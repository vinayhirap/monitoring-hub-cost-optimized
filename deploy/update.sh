#!/bin/bash
set -e

APP_DIR="/opt/monitoring-hub"
REPO_DIR="$APP_DIR/app"
VENV_DIR="$APP_DIR/venv"

echo "=== Updating ASLOps Monitoring Hub ==="

cd "$REPO_DIR"

# ── Pull latest ──────────────────────────────────────────────
git pull origin main
echo "--- Code updated ---"

# ── Update Python deps if requirements changed ───────────────
source "$VENV_DIR/bin/activate"
pip install -r requirements.txt --quiet

# ── Rebuild frontend if changed ──────────────────────────────
cd "$REPO_DIR/frontend"
npm install --silent
npm run build
echo "--- Frontend rebuilt ---"

# ── Restart backend ──────────────────────────────────────────
sudo systemctl restart monitoring-hub
echo "--- Service restarted ---"

sudo systemctl status monitoring-hub --no-pager
echo "=== Update complete ==="