#!/usr/bin/env bash
# deploy.sh — Pull latest code and restart services on VPS
# Usage: bash deploy.sh

set -euo pipefail

BOTDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BOTDIR"

echo "=== $(date) — Starting deploy ==="

# Pull latest code
git pull --ff-only origin main

# Activate venv if it exists
if [ -d ".venv" ]; then
  source .venv/bin/activate
fi

# Install/update Python dependencies
pip install -r requirements.txt -q

# Run database migration (idempotent — safe to run every deploy)
python3 migrate.py

# Restart services
if systemctl is-active --quiet boterx-bot; then
  echo "Restarting boterx-bot..."
  sudo systemctl restart boterx-bot
fi

if systemctl is-active --quiet boterx; then
  echo "Reloading boterx (gunicorn)..."
  sudo systemctl reload boterx || sudo systemctl restart boterx
fi

echo "=== Deploy complete ==="
