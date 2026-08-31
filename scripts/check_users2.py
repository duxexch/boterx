import paramiko, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

# Check what /users returns
stdin, stdout, stderr = ssh.exec_command("curl -s 'http://127.0.0.1:8080/users'", timeout=15)
html = stdout.read().decode('utf-8', 'ignore')
print("=== /users raw response ===")
print(repr(html[:500]))
print("---")
print(html[:1000])

# Check if there's a login redirect
print("\n=== Following redirects ===")
stdin, stdout, stderr = ssh.exec_command("curl -sv 'http://127.0.0.1:8080/users' 2>&1 | grep -i 'location\\|HTTP\\|302\\|301'", timeout=15)
print(stdout.read().decode('utf-8', 'ignore')[:500])

# Check the login endpoint
print("\n=== Login page ===")
stdin, stdout, stderr = ssh.exec_command("curl -s 'http://127.0.0.1:8080/login' | head -20", timeout=15)
print(stdout.read().decode('utf-8', 'ignore')[:500])

# Try authenticating and then accessing /users
print("\n=== Auth and access users ===")
stdin, stdout, stderr = ssh.exec_command("curl -s -c /tmp/auth_cookies.txt -X POST 'http://127.0.0.1:8080/login' -H 'Content-Type: application/x-www-form-urlencoded' -d 'admin_id=7146701713&password=Vex-LN36X_SG3bv-UNooqkME' -v 2>&1 | grep -i 'location\\|HTTP\\|Set-Cookie'", timeout=15)
print(stdout.read().decode('utf-8', 'ignore')[:500])

# Now use the auth cookies to access /users
stdin, stdout, stderr = ssh.exec_command("curl -s -b /tmp/auth_cookies.txt 'http://127.0.0.1:8080/users' | wc -c", timeout=15)
print("\n/users page size with auth: " + stdout.read().decode('utf-8', 'ignore').strip())

stdin, stdout, stderr = ssh.exec_command("curl -s -b /tmp/auth_cookies.txt 'http://127.0.0.1:8080/users' | head -50", timeout=15)
print(stdout.read().decode('utf-8', 'ignore')[:1500])

ssh.close()
