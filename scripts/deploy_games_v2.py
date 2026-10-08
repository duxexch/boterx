#!/usr/bin/env python3
"""Deploy all game improvements to production."""
import paramiko

SERVER = '69.169.108.197'
USER = 'root'
PASS = 'M12122099m@@@@'
REMOTE_DIR = '/opt/bot'

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(SERVER, username=USER, password=PASS, timeout=15)
print(f"Connected to {SERVER}")

sftp = ssh.open_sftp()
files = [
    ('dashboard/templates/dice.html', f'{REMOTE_DIR}/dashboard/templates/dice.html'),
    ('dashboard/templates/mines.html', f'{REMOTE_DIR}/dashboard/templates/mines.html'),
    ('dashboard/templates/plinko.html', f'{REMOTE_DIR}/dashboard/templates/plinko.html'),
    ('dashboard/templates/wheel.html', f'{REMOTE_DIR}/dashboard/templates/wheel.html'),
    ('dashboard/templates/snatch.html', f'{REMOTE_DIR}/dashboard/templates/snatch.html'),
    ('dashboard/templates/aviator.html', f'{REMOTE_DIR}/dashboard/templates/aviator.html'),
    ('dashboard/templates/crash.html', f'{REMOTE_DIR}/dashboard/templates/crash.html'),
    ('dashboard/templates/lottery.html', f'{REMOTE_DIR}/dashboard/templates/lottery.html'),
]
for local, remote in files:
    print(f"Uploading {local.split('/')[-1]}...")
    sftp.put(local, remote)
sftp.close()

print("Restarting service...")
stdin, stdout, stderr = ssh.exec_command('systemctl restart boterx-dashboard.service', timeout=30)
stdout.read()

import time; time.sleep(3)

stdin, stdout, stderr = ssh.exec_command('systemctl is-active boterx-dashboard.service')
print(f"Service: {stdout.read().decode().strip()}")

stdin, stdout, stderr = ssh.exec_command('curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/webapp/games')
print(f"Games hub: {stdout.read().decode().strip()}")

ssh.close()
print("Deploy complete!")
