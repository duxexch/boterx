import paramiko, sys
sys.stdout.reconfigure(encoding='utf-8')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@')

# 1. Check dashboard service
stdin, stdout, stderr = ssh.exec_command('systemctl is-active boterx-dashboard 2>&1')
print(f'Dashboard: {stdout.read().decode().strip()}')

# 2. Check dashboard logs for errors
stdin, stdout, stderr = ssh.exec_command('journalctl -u boterx-dashboard --no-pager -n 30 2>&1')
print(f'\n=== Dashboard logs ===\n{stdout.read().decode().strip()[:2000]}')

# 3. Test dashboard API directly
stdin, stdout, stderr = ssh.exec_command('curl -s http://localhost:8080/api/stats 2>&1')
print(f'\n=== /api/stats (no auth) ===\n{stdout.read().decode().strip()[:500]}')

# 4. Test login API
stdin, stdout, stderr = ssh.exec_command('curl -s -X POST http://localhost:8080/login -H "Content-Type: application/x-www-form-urlencoded" -d "admin_id=7146701713&password=boterx_admin_2026" 2>&1')
print(f'\n=== Login attempt ===\n{stdout.read().decode().strip()[:500]}')

# 5. Check nginx
stdin, stdout, stderr = ssh.exec_command('systemctl is-active nginx 2>&1')
print(f'\nNginx: {stdout.read().decode().strip()}')

# 6. Check if dashboard is accessible via HTTPS
stdin, stdout, stderr = ssh.exec_command('curl -sk -o /dev/null -w "%{http_code}" https://69.169.108.197.sslip.io/dashboard 2>&1')
print(f'\nHTTPS /dashboard: {stdout.read().decode().strip()}')

# 7. Check games API
stdin, stdout, stderr = ssh.exec_command('curl -s http://localhost:8080/api/games/list 2>&1')
print(f'\n=== /api/games/list ===\n{stdout.read().decode().strip()[:500]}')

# 8. Check games_catalog
stdin, stdout, stderr = ssh.exec_command('cat /opt/bot/games_catalog.csv 2>/dev/null')
print(f'\n=== games_catalog.csv ===\n{stdout.read().decode().strip()[:500]}')

# 9. Check users.csv for game_balance column
stdin, stdout, stderr = ssh.exec_command('head -1 /opt/bot/users.csv 2>/dev/null')
print(f'\n=== users.csv header ===\n{stdout.read().decode().strip()[:500]}')

ssh.close()
