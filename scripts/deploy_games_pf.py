#!/usr/bin/env python3
"""Deploy game PF improvements to production server."""
import paramiko
import sys

SERVER = '69.169.108.197'
USER = 'root'
PASS = 'M12122099m@@@@'
REMOTE_DIR = '/opt/bot'

def run(cmd):
    print(f"  > {cmd[:120]}")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=60)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    if err.strip():
        print(f"  ! stderr: {err.strip()[:200]}")
    return out.strip()

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(SERVER, username=USER, password=PASS, timeout=15)
print(f"Connected to {SERVER}")

# Upload files
sftp = ssh.open_sftp()
files = [
    ('provably_fair.py', f'{REMOTE_DIR}/provably_fair.py'),
    ('dashboard/dice_engine.py', f'{REMOTE_DIR}/dashboard/dice_engine.py'),
    ('dashboard/app.py', f'{REMOTE_DIR}/dashboard/app.py'),
    ('dashboard/static/js/game-base.js', f'{REMOTE_DIR}/dashboard/static/js/game-base.js'),
    ('dashboard/static/css/game-base.css', f'{REMOTE_DIR}/dashboard/static/css/game-base.css'),
]

for local, remote in files:
    print(f"Uploading {local}...")
    sftp.put(local, remote)
sftp.close()

# Restart service
print("Restarting dashboard service...")
run('systemctl restart boterx-dashboard.service')

import time
time.sleep(3)

# Health check
print("Health check...")
out = run('systemctl is-active boterx-dashboard.service')
print(f"Service status: {out}")

out = run('curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/webapp/games')
print(f"Games hub HTTP: {out}")

ssh.close()
print("Deploy complete!")
