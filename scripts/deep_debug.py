import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

print("=== 1. FULL SERVICE LOGS (last 50 lines) ===")
s, o, e = ssh.exec_command("journalctl -u boterx-dashboard.service -n 50 --no-pager", timeout=15)
out = o.read().decode('utf-8', 'ignore').strip()
print(out)

print("\n=== 2. NGINX ACCESS LOGS (last 20) ===")
s, o, e = ssh.exec_command("tail -20 /var/log/nginx/access.log 2>/dev/null || tail -20 /var/log/nginx/access.log.1 2>/dev/null || echo 'No nginx logs'", timeout=15)
out = o.read().decode('utf-8', 'ignore').strip()
print(out)

print("\n=== 3. NGINX ERROR LOGS (last 20) ===")
s, o, e = ssh.exec_command("tail -20 /var/log/nginx/error.log 2>/dev/null || echo 'No nginx error logs'", timeout=15)
out = o.read().decode('utf-8', 'ignore').strip()
print(out)

print("\n=== 4. CHECK ACTUAL FILES ON SERVER ===")
s, o, e = ssh.exec_command("ls -la /opt/bot/dashboard/static/js/*.js", timeout=10)
out = o.read().decode('utf-8', 'ignore').strip()
print(out)

print("\n=== 5. CHECK BASE.HTML ON SERVER ===")
s, o, e = ssh.exec_command("grep -n 'script src' /opt/bot/dashboard/templates/base.html", timeout=10)
out = o.read().decode('utf-8', 'ignore').strip()
print(out)

print("\n=== 6. TEST LOGIN + DASHBOARD WITH FULL HTML ===")
ssh.exec_command('curl -s -c /tmp/cookies.txt "http://127.0.0.1:8080/vex/admin/admin" -d "admin_id=7146701713&password=Vex-LN36X_SG3bv-UNooqkME" > /dev/null', timeout=30)
s, o, e = ssh.exec_command('curl -s -b /tmp/cookies.txt "http://127.0.0.1:8080/dashboard"', timeout=30)
out = o.read().decode('utf-8', 'ignore').strip()
with open("full_dashboard.html", "w", encoding="utf-8") as f:
    f.write(out)
print(f"Dashboard HTML length: {len(out)} chars")
print("First 200 chars:", out[:200])
print("...")

print("\n=== 7. CHECK FOR JS ERRORS IN DASHBOARD HTML ===")
for pattern in ['ReferenceError', 't is not defined', 'notifications is not defined', 'activityTicker is not defined', 'copied is not defined', 'tr is not defined', 'fmtNum is not defined', 'Alpine is not defined']:
    s, o, e = ssh.exec_command(f'curl -s -b /tmp/cookies.txt "http://127.0.0.1:8080/dashboard" | grep -c "{pattern}"', timeout=15)
    out = o.read().decode('utf-8', 'ignore').strip()
    if out != '0':
        print(f"  FOUND: {pattern} = {out}")

ssh.close()