import paramiko, sys, json
sys.stdout.reconfigure(encoding='utf-8')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@')

# 1. Check if /api/stats returns data (with session)
# First login
stdin, stdout, stderr = ssh.exec_command('curl -s -c /tmp/cookies.txt -X POST http://localhost:8080/login -H "Content-Type: application/x-www-form-urlencoded" -d "admin_id=7146701713&password=boterx_admin_2026" -L -o /dev/null -w "%{http_code}" 2>&1')
login_status = stdout.read().decode().strip()
print(f'Login: {login_status}')

# Then get stats
stdin, stdout, stderr = ssh.exec_command('curl -s -b /tmp/cookies.txt http://localhost:8080/api/stats 2>&1')
stats = stdout.read().decode().strip()
print(f'\n=== /api/stats ===')
try:
    d = json.loads(stats)
    print(f'users.total: {d.get("users",{}).get("total","?")}')
    print(f'users.today: {d.get("users",{}).get("today","?")}')
    print(f'transactions.pending: {d.get("transactions",{}).get("pending","?")}')
    print(f'transactions.approved: {d.get("transactions",{}).get("approved","?")}')
    print(f'volume.today: {d.get("volume",{}).get("today","?")}')
    print(f'matches.active: {d.get("matches",{}).get("active","?")}')
    print(f'lottery.participants: {d.get("lottery",{}).get("participants","?")}')
except:
    print(stats[:500])

# 2. Check transactions.csv
stdin, stdout, stderr = ssh.exec_command('wc -l /opt/bot/transactions.csv 2>&1')
print(f'\n=== transactions.csv lines ===')
print(stdout.read().decode().strip())

# 3. Check users.csv
stdin, stdout, stderr = ssh.exec_command('wc -l /opt/bot/users.csv 2>&1')
print(f'\n=== users.csv lines ===')
print(stdout.read().decode().strip())

# 4. Check dashboard logs for errors
stdin, stdout, stderr = ssh.exec_command('journalctl -u boterx-dashboard --no-pager -n 10 2>&1')
print(f'\n=== Dashboard logs ===')
print(stdout.read().decode().strip()[:1000])

# 5. Check /api/stats/live
stdin, stdout, stderr = ssh.exec_command('curl -s -b /tmp/cookies.txt http://localhost:8080/api/stats/live 2>&1 | head -c 500')
print(f'\n=== /api/stats/live ===')
print(stdout.read().decode().strip())

# 6. Check CSS file exists
stdin, stdout, stderr = ssh.exec_command('ls -la /opt/bot/dashboard/static/css/style.css 2>&1')
print(f'\n=== style.css ===')
print(stdout.read().decode().strip())

ssh.close()
