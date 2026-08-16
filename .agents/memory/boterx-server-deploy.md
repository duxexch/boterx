---
name: Boterx server deploy
description: How to deploy code updates to the production server, service names, and post-deploy checks
---

# Boterx Server Deploy

## Server
- IP: 69.169.108.197, root password in session (do not store here)
- OS: Ubuntu 24.04, 1 CPU, 1.9 GB RAM
- Code lives at: /opt/bot/
- Git remote: github.com/duxexch/boterx (main branch)

## Deploy commands
```bash
cd /opt/bot
git fetch origin main
git reset --hard origin/main
python3 migrate.py   # idempotent — safe to run every time
systemctl restart boterx boterx-dashboard
sleep 3
systemctl is-active boterx boterx-dashboard
curl -sf http://localhost:8080/health | python3 -m json.tool
```

## No-GitHub deploy path (used when GitHub push is unavailable)
```bash
git bundle create /tmp/boterx.bundle <server-head>..main   # locally
sshpass -e scp /tmp/boterx.bundle root@69.169.108.197:/tmp/
ssh: cd /opt/bot && git fetch /tmp/boterx.bundle main && git reset --hard FETCH_HEAD
```
SSH access: `export SSHPASS="$SERVER_ROOT_PASSWORD"` (Replit secret) then `sshpass -e ssh root@...`.

## Production mode (since Aug 2026)
- boterx-dashboard.service runs with `Environment=APP_ENV=production` + strong DASHBOARD_PASSWORD/DASHBOARD_SECRET_KEY set in the unit file (not .env).
- Production refuses to start with the known default password `boterx_admin_2026` — never revert those Environment lines.
- Admin login: POST /vex/admin/admin needs the csrf_token from the GET form; success = 303.

## Services
- `boterx.service` — Telegram bot (venv Python, comprehensive_bot.py)
- `boterx-dashboard.service` — gunicorn on port 8080 (system Python, dashboard/app.py)

## Domain & SSL
- vex.deals + 69.169.108.197.sslip.io, both SSL via Certbot/nginx

## Python environments
- Bot venv: /opt/bot/venv — only python-dotenv + openpyxl installed
- Dashboard uses system Python (Flask/gunicorn system-wide)
- Do NOT install Flask in bot venv unless needed

## Post-deploy health check
- `curl localhost:8080/health` → JSON {"status":"ok"}
- `curl -o /dev/null -w "%{http_code}" localhost:8080/` → 200 (landing page)

**Why:** git push is not enough — server must pull explicitly; migrate.py handles schema changes idempotently; always verify both services active before declaring done.
