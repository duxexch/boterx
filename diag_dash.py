import paramiko, sys, json
sys.stdout.reconfigure(encoding='utf-8')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@')

# 1. Test login flow
stdin, stdout, stderr = ssh.exec_command('curl -s -c /tmp/cookies.txt -X POST http://localhost:8080/login -d "admin_id=7146701713&password=boterx_admin_2026" -L -w "\\n%{http_code}" 2>&1 | tail -5')
print(f'=== Login ===\n{stdout.read().decode().strip()[:500]}')

# 2. Test /api/stats with cookies
stdin, stdout, stderr = ssh.exec_command('curl -s -b /tmp/cookies.txt http://localhost:8080/api/stats 2>&1')
resp = stdout.read().decode().strip()
print(f'\n=== /api/stats (with auth) ===\n{resp[:800]}')

# 3. Test /api/stats/live (SSE)
stdin, stdout, stderr = ssh.exec_command('curl -s -b /tmp/cookies.txt http://localhost:8080/api/stats/live --max-time 3 2>&1')
resp2 = stdout.read().decode().strip()
print(f'\n=== /api/stats/live ===\n{resp2[:500]}')

# 4. Check dashboard HTML response
stdin, stdout, stderr = ssh.exec_command('curl -s -b /tmp/cookies.txt http://localhost:8080/dashboard 2>&1 | head -20')
print(f'\n=== /dashboard HTML ===\n{stdout.read().decode().strip()[:500]}')

# 5. Check if CSS is loaded
stdin, stdout, stderr = ssh.exec_command('curl -s -o /dev/null -w "%{http_code}" -b /tmp/cookies.txt http://localhost:8080/static/css/style.css 2>&1')
print(f'\nCSS status: {stdout.read().decode().strip()}')

# 6. Check if app.js is loaded
stdin, stdout, stderr = ssh.exec_command('curl -s -o /dev/null -w "%{http_code}" -b /tmp/cookies.txt http://localhost:8080/static/js/app.js 2>&1')
print(f'JS status: {stdout.read().decode().strip()}')

# 7. Check dashboard logs for errors
stdin, stdout, stderr = ssh.exec_command('journalctl -u boterx-dashboard --no-pager -n 15 2>&1')
print(f'\n=== Dashboard logs ===\n{stdout.read().decode().strip()[:1500]}')

ssh.close()
