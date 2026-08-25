import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

# Check script order
s, o, e = ssh.exec_command("grep -n 'static/js/' /opt/bot/dashboard/templates/base.html | head -10", timeout=15)
out = o.read().decode('utf-8', 'ignore').strip()
print("=== SCRIPT ORDER ===")
print(out)

# Check version
s, o, e = ssh.exec_command("grep 'v=20260825a' /opt/bot/dashboard/templates/base.html | head -5", timeout=15)
out = o.read().decode('utf-8', 'ignore').strip()
print("\n=== VERSION ===")
print(out)

# Check window.tr in runtime
s, o, e = ssh.exec_command("curl -s 'http://127.0.0.1:8080/static/js/i18n-admin-runtime.js?v=20260825a' | tail -c 200", timeout=15)
out = o.read().decode('utf-8', 'ignore').strip()
print("\n=== WINDOW.TR IN RUNTIME ===")
print(out)

# Check base-app.js has fallback
s, o, e = ssh.exec_command("curl -s 'http://127.0.0.1:8080/static/js/base-app.js?v=20260825a' | grep -n 'window.tr\\|window.fmtNum' | head -5", timeout=15)
out = o.read().decode('utf-8', 'ignore').strip()
print("\n=== BASE-APP FALLBACKS ===")
print(out)

# Check api usage in base-app
s, o, e = ssh.exec_command("curl -s 'http://127.0.0.1:8080/static/js/base-app.js?v=20260825a' | grep -n 'window.api' | head -5", timeout=15)
out = o.read().decode('utf-8', 'ignore').strip()
print("\n=== API USAGE ===")
print(out)

ssh.close()