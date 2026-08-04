#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import paramiko, time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@')

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd)
    return stdout.read().decode('utf-8', errors='replace').strip()

print("=== quick_deposits.csv ===")
print(run('cat /opt/bot/quick_deposits.csv'))

print("\n=== transactions.csv (last 5) ===")
print(run('tail -5 /opt/bot/transactions.csv'))

print("\n=== player_payment_methods.csv ===")
print(run('cat /opt/bot/player_payment_methods.csv'))

print("\n=== users.csv game_balance column ===")
print(run('head -1 /opt/bot/users.csv'))
print(run('cut -d, -f1,2,15 /opt/bot/users.csv'))

print("\n=== Check if approve_deposit adds balance ===")
# Search for approve_deposit in game_engine.py
print(run('grep -n "def approve_deposit" /opt/bot/game_engine.py'))
print(run('grep -A 20 "def approve_deposit" /opt/bot/game_engine.py'))

print("\n=== Check bot notification for game deposits ===")
# Search for notification code in handle_game_deposit or similar
print(run('grep -n "gamedep\\|game_deposit\\|handle_game\\|إيداع محفظة" /opt/bot/comprehensive_bot.py | head -20'))

print("\n=== Dashboard pending deposits API ===")
print(run('curl -s http://localhost:8080/api/deposit/pending 2>&1 | head -c 300'))

print("\n=== Bot logs (last 20) ===")
print(run('journalctl -u boterx --no-pager -n 20 2>&1'))

print("\n=== Dashboard logs (last 20) ===")
print(run('journalctl -u boterx-dashboard --no-pager -n 20 2>&1'))

ssh.close()
