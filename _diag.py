#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@')

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd)
    return stdout.read().decode('utf-8', errors='replace').strip()

# Check recent bot logs for any errors
print("=== Recent bot logs (last 50 lines) ===")
logs = run('journalctl -u boterx --no-pager -n 50 2>&1')
for line in logs.split('\n'):
    if any(kw in line for kw in ['Error', 'error', 'Traceback', 'Exception', 'show_games', 'games_hub', 'ألعاب']):
        print(line)

# Test show_games_hub directly
print("\n=== Python import test ===")
print(run('cd /opt/bot && python3 -c "from game_engine import GameManager; gm = GameManager(); print(\'OK balance:\', gm.get_balance(7146701713))" 2>&1'))

# Check if games_catalog exists and has data
print("\n=== games_catalog.csv ===")
print(run('cat /opt/bot/games_catalog.csv | head -3'))

# Check if the URL in show_games_hub is correct
print("\n=== dashboard_url setting ===")
print(run('cat /opt/bot/system_settings.csv 2>/dev/null | grep dashboard_url'))

# Check if https works
print("\n=== curl games hub ===")
print(run('curl -s -o /dev/null -w "%{http_code}" https://69.169.108.197.sslip.io/webapp/games?uid=7146701713 2>&1'))

# Check if the issue is the web_app button — send a test message via bot API
print("\n=== Bot getMe ===")
token = run('grep BOT_TOKEN /opt/bot/.env | cut -d= -f2')
print(f"Token: {token[:15]}...")

ssh.close()
