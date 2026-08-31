import paramiko, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

# Check error logs
stdin, stdout, stderr = ssh.exec_command("tail -50 /opt/bot/logs/error.log 2>/dev/null || journalctl -u boterx-dashboard --no-pager -n 50 2>/dev/null || tail -50 /var/log/gunicorn/error.log 2>/dev/null", timeout=10)
print("=== ERROR LOGS ===")
print(stdout.read().decode('utf-8', 'ignore')[:3000])

# Also check systemd logs
stdin, stdout, stderr = ssh.exec_command("journalctl -u boterx-dashboard --since '10 min ago' --no-pager 2>/dev/null | tail -30", timeout=10)
print("\n=== SYSTEMD LOGS ===")
print(stdout.read().decode('utf-8', 'ignore')[:3000])

# Test the page
stdin, stdout, stderr = ssh.exec_command("curl -s -b /tmp/final_cookies.txt 'https://vex.deals/dashboard' -o /dev/null -w 'HTTP: %{http_code} Size: %{size_download}' 2>/dev/null", timeout=10)
print("\n=== DASHBOARD TEST ===")
print(stdout.read().decode('utf-8', 'ignore').strip())

# Test a few pages
for p in ['dashboard', 'users', 'games', 'rental']:
    stdin, stdout, stderr = ssh.exec_command(f"curl -sk -b /tmp/final_cookies.txt 'https://vex.deals/{p}' -o /dev/null -w '{p}: HTTP %{{http_code}}' 2>/dev/null", timeout=10)
    print(stdout.read().decode('utf-8', 'ignore').strip())

# Check if gunicorn is still running
stdin, stdout, stderr = ssh.exec_command("systemctl is-active boterx-dashboard && ps aux | grep gunicorn | grep -v grep | wc -l", timeout=10)
print("\n=== SERVICE STATUS ===")
print(stdout.read().decode('utf-8', 'ignore').strip())

ssh.close()
