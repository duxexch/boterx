import paramiko, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

# Login via HTTPS (cookie is Secure-only), then access /users
stdin, stdout, stderr = ssh.exec_command("""curl -sk -c /tmp/https_cookies.txt -X POST 'https://vex.deals/vex/admin/admin' -H 'Content-Type: application/x-www-form-urlencoded' -d 'admin_id=7146701713&password=Vex-LN36X_SG3bv-UNooqkME' -v 2>&1 | grep -i 'location\\|set-cookie\\|HTTP/'""", timeout=15)
print("=== HTTPS Login ===")
print(stdout.read().decode('utf-8', 'ignore')[:500])

stdin, stdout, stderr = ssh.exec_command("cat /tmp/https_cookies.txt 2>/dev/null", timeout=10)
print("\n=== HTTPS Cookies ===")
print(stdout.read().decode('utf-8', 'ignore')[:500])

# Now access /users with HTTPS cookies
stdin, stdout, stderr = ssh.exec_command("curl -sk -b /tmp/https_cookies.txt 'https://vex.deals/users' | wc -c", timeout=15)
size = stdout.read().decode('utf-8', 'ignore').strip()
print(f"\n=== /users via HTTPS size: {size} ===")

if int(size or 0) > 500:
    stdin, stdout, stderr = ssh.exec_command("curl -sk -b /tmp/https_cookies.txt 'https://vex.deals/users' 2>/dev/null", timeout=15)
    html = stdout.read().decode('utf-8', 'ignore')
    print(html[:3000])
else:
    stdin, stdout, stderr = ssh.exec_command("curl -sk -b /tmp/https_cookies.txt 'https://vex.deals/users' 2>/dev/null", timeout=15)
    print(stdout.read().decode('utf-8', 'ignore')[:1000])

ssh.close()
