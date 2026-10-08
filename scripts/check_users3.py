import paramiko, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

# Check the actual login route - is it JSON or form?
stdin, stdout, stderr = ssh.exec_command("grep -n 'def login\\|/login\\|@app.route.*login' /opt/bot/dashboard/app.py | head -20", timeout=10)
print("=== Login routes ===")
print(stdout.read().decode('utf-8', 'ignore'))

# Check the /vex/admin/admin route
stdin, stdout, stderr = ssh.exec_command("grep -n '/vex/admin/admin\\|admin_redirect\\|admin_login' /opt/bot/dashboard/app.py | head -20", timeout=10)
print("\n=== /vex/admin/admin route ===")
print(stdout.read().decode('utf-8', 'ignore'))

# Check session cookie handling
stdin, stdout, stderr = ssh.exec_command("grep -n 'session\\|SESSION_COOKIE\\|SECRET_KEY\\|before_request' /opt/bot/dashboard/app.py | head -30", timeout=10)
print("\n=== Session config ===")
print(stdout.read().decode('utf-8', 'ignore'))

# Do a proper login flow
print("\n=== Login flow test ===")
stdin, stdout, stderr = ssh.exec_command("""curl -sv -c /tmp/proper_cookies.txt -X POST 'http://127.0.0.1:8080/vex/admin/admin' -H 'Content-Type: application/x-www-form-urlencoded' -d 'admin_id=7146701713&password=Vex-LN36X_SG3bv-UNooqkME' 2>&1 | grep -i 'location\\|set-cookie\\|HTTP/'""", timeout=15)
print(stdout.read().decode('utf-8', 'ignore')[:500])

# Try JSON login
stdin, stdout, stderr = ssh.exec_command("""curl -sv -c /tmp/proper_cookies.txt -X POST 'http://127.0.0.1:8080/vex/admin/admin' -H 'Content-Type: application/json' -d '{"admin_id":"7146701713","password":"Vex-LN36X_SG3bv-UNooqkME"}' 2>&1 | grep -i 'location\\|set-cookie\\|HTTP/'""", timeout=15)
print("\n=== JSON Login ===")
print(stdout.read().decode('utf-8', 'ignore')[:500])

# Check actual session cookie file
stdin, stdout, stderr = ssh.exec_command("cat /tmp/proper_cookies.txt 2>/dev/null", timeout=10)
print("\n=== Cookies ===")
print(stdout.read().decode('utf-8', 'ignore')[:500])

# Access /users with auth cookies
stdin, stdout, stderr = ssh.exec_command("curl -s -b /tmp/proper_cookies.txt 'http://127.0.0.1:8080/users' | wc -c", timeout=15)
size = stdout.read().decode('utf-8', 'ignore').strip()
print(f"\n=== /users size with auth: {size} ===")

stdin, stdout, stderr = ssh.exec_command("curl -s -b /tmp/proper_cookies.txt 'http://127.0.0.1:8080/users' 2>/dev/null", timeout=15)
html = stdout.read().decode('utf-8', 'ignore')
print(html[:2000])

ssh.close()
