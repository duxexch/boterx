import paramiko, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

# Fetch users.html page source
stdin, stdout, stderr = ssh.exec_command("curl -s 'http://127.0.0.1:8080/users' -b 'session=test; logged_in=1'", timeout=15)
html = stdout.read().decode('utf-8', 'ignore')
print(f"Page length: {len(html)}")
print(f"Has usersApp: {'usersApp' in html}")

# Check the api function in served app.js
stdin, stdout, stderr = ssh.exec_command("curl -s 'http://127.0.0.1:8080/static/js/app.js' | head -100", timeout=10)
appjs = stdout.read().decode('utf-8', 'ignore')
print(f"\n=== app.js first 100 lines ===")
print(appjs[:2000])

# Check if users.html page actually loads with auth
stdin, stdout, stderr = ssh.exec_command("curl -sv 'http://127.0.0.1:8080/api/users?page=1&per_page=2' -b /tmp/browser_cookies.txt 2>&1 | head -30", timeout=10)
print(f"\n=== API with browser cookies ===")
print(stdout.read().decode('utf-8', 'ignore')[:1000])

# Check what the browser ACTUALLY gets - simulate browser fetch with Accept header
stdin, stdout, stderr = ssh.exec_command("""curl -s 'http://127.0.0.1:8080/api/users?page=1&per_page=2' -H 'Accept: application/json' -b /tmp/browser_cookies.txt -w '\\nHTTP_CODE:%{http_code}\\nCONTENT_TYPE:%{content_type}'""", timeout=10)
resp = stdout.read().decode('utf-8', 'ignore')
print(f"\n=== Browser-simulated API response ===")
print(resp[:500])

# Check nginx config for proxy issues
stdin, stdout, stderr = ssh.exec_command("cat /etc/nginx/sites-enabled/vex.deals.conf 2>/dev/null || cat /etc/nginx/conf.d/vex*.conf 2>/dev/null || echo 'no nginx conf found'", timeout=10)
print(f"\n=== Nginx config ===")
print(stdout.read().decode('utf-8', 'ignore')[:2000])

# Check if there's a CSRF or session issue
stdin, stdout, stderr = ssh.exec_command("python3 -c \"import sqlite3; conn=sqlite3.connect('/opt/bot/boterx.db'); c=conn.cursor(); c.execute('SELECT count(*) FROM users'); print('DB users:', c.fetchone()[0])\"", timeout=10)
print(f"\n=== DB check ===")
print(stdout.read().decode('utf-8', 'ignore').strip())

# Check the ACTUAL app.js api() function on the server
stdin, stdout, stderr = ssh.exec_command("grep -n 'async function api' /opt/bot/dashboard/static/js/app.js", timeout=10)
print(f"\n=== api() location on server ===")
print(stdout.read().decode('utf-8', 'ignore').strip())

stdin, stdout, stderr = ssh.exec_command("sed -n '740,770p' /opt/bot/dashboard/static/js/app.js", timeout=10)
print(f"\n=== api() function on server ===")
print(stdout.read().decode('utf-8', 'ignore'))

ssh.close()
