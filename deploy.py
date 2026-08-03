import paramiko, sys, time
sys.stdout.reconfigure(encoding='utf-8')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@')

commands = [
    'systemctl stop boterx 2>&1',
    'cd /opt/bot && git stash 2>&1',
    'cd /opt/bot && git pull origin main 2>&1',
    'find /opt/bot -name "__pycache__" -type d -exec rm -rf {} + 2>&1',
    'systemctl start boterx 2>&1',
    'systemctl start boterx-dashboard 2>&1',
]

for cmd in commands:
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode('utf-8').strip()
    if out:
        print(f'$ {cmd[:60]}')
        print(f'  {out[:200]}')

time.sleep(3)
stdin, stdout, stderr = ssh.exec_command('systemctl is-active boterx 2>&1')
print(f'\nBot: {stdout.read().decode().strip()}')
stdin, stdout, stderr = ssh.exec_command('systemctl is-active boterx-dashboard 2>&1')
print(f'Dashboard: {stdout.read().decode().strip()}')
stdin, stdout, stderr = ssh.exec_command('journalctl -u boterx --no-pager -n 5 2>&1')
print(f'\nLogs:\n{stdout.read().decode().strip()}')

ssh.close()
