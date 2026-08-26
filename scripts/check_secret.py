import paramiko, time, sys
sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

def run(cmd, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    return stdout.read().decode('utf-8', 'ignore').strip(), stderr.read().decode('utf-8', 'ignore').strip()

print('=== Check DASHBOARD_SECRET_KEY in .env ===')
out, _ = run('grep DASHBOARD_SECRET_KEY /opt/bot/.env 2>/dev/null || echo "NOT FOUND"')
print(out)

print('\n=== Check all env secrets ===')
out, _ = run('grep -i "secret\\|key\\|token" /opt/bot/.env 2>/dev/null | head -10')
print(out)

print('\n=== Check app.py SECRET_KEY line ===')
out, _ = run('sed -n "58,78p" /opt/bot/dashboard/app.py')
print(out)

ssh.close()
