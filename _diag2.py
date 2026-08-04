#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@')

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd)
    return stdout.read().decode('utf-8', errors='replace').strip()

# Check if user 8038414871 exists in users.csv
print("=== User 8038414871 ===")
print(run('grep 8038414871 /opt/bot/users.csv 2>/dev/null || echo "NOT FOUND"'))

# Check more detailed logs — maybe show_games_hub is crashing silently
print("\n=== Full recent logs ===")
print(run('journalctl -u boterx --no-pager -n 30 2>&1'))

# Check if bot is actually sending messages back
print("\n=== Check if show_games_hub sends anything ===")
print(run('journalctl -u boterx --no-pager -n 30 2>&1 | grep -i "game\\|hub\\|error\\|fail\\|send"'))

ssh.close()
