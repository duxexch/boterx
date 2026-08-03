import paramiko, sys
sys.stdout.reconfigure(encoding='utf-8')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@')

commands = [
    # 1. Stop services
    'systemctl stop boterx 2>&1',
    'systemctl stop boterx-dashboard 2>&1',
    
    # 2. Pull latest from git
    'cd /opt/bot && git add -A 2>&1',
    'cd /opt/bot && git stash 2>&1',
    'cd /opt/bot && git pull origin main 2>&1',
    
    # 3. Clear Python cache
    'find /opt/bot -name "__pycache__" -type d -exec rm -rf {} + 2>&1',
    'find /opt/bot -name "*.pyc" -delete 2>&1',
    
    # 4. Clear temp files
    'rm -f /opt/bot/conv_*.txt /opt/bot/check_*.py /opt/bot/clean_*.py /opt/bot/debug_*.py /opt/bot/test_*.py /opt/bot/find_*.py /opt/bot/auto_*.py /opt/bot/add_*.py /opt/bot/extract_*.py /opt/bot/update_*.py /opt/bot/translate_*.py 2>&1',
    
    # 5. Restart services
    'systemctl start boterx 2>&1',
    'systemctl start boterx-dashboard 2>&1',
    
    # 6. Check status
    'systemctl is-active boterx 2>&1',
    'systemctl is-active boterx-dashboard 2>&1',
]

for cmd in commands:
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode('utf-8').strip()
    err = stderr.read().decode('utf-8').strip()
    if out:
        print(f'$ {cmd}')
        print(f'  {out}')
    if err:
        print(f'  ERR: {err}')

ssh.close()
print('\nDone!')
