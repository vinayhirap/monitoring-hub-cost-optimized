#!/bin/bash
set -e

echo "=== ASLOps Monitoring Hub — Server Setup ==="

# ── System packages ──────────────────────────────────────────
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv mysql-server nginx git curl

# ── MySQL setup ──────────────────────────────────────────────
sudo systemctl start mysql
sudo systemctl enable mysql

# Create DB + user
sudo mysql -e "
CREATE DATABASE IF NOT EXISTS monitoring_hub CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'monitor'@'localhost' IDENTIFIED BY 'root123';
GRANT ALL PRIVILEGES ON monitoring_hub.* TO 'monitor'@'localhost';
FLUSH PRIVILEGES;
"

echo "=== MySQL ready ==="

# ── App directory ────────────────────────────────────────────
sudo mkdir -p /opt/monitoring-hub
sudo chown $USER:$USER /opt/monitoring-hub

echo "=== Setup complete. Run deploy.sh next ==="