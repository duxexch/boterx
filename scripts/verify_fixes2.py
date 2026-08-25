import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

# Check full script order
s, o, e = ssh.exec_command("cat /opt/bot/dashboard/templates/base.html | grep -n 'script src'", timeout=15)
out = o.read().decode('utf-8', 'ignore').strip()
print("=== FULL SCRIPT ORDER ===")
print(out)

# Check window.tr export in runtime
s, o, e = ssh.exec_command("curl -s 'http://127.0.0.1:8080/static/js/i18n-admin-runtime.js?v=20260825a' | grep -n 'window.tr'", timeout=15)
out = o.read().decode('utf-8', 'ignore').strip()
print("\n=== WINDOW.TR EXPORT ===")
print(out)

# Check init error handling
s, o, e = ssh.exec_command("curl -s 'http://127.0.0.1:8080/static/js/base-app.js?v=20260825a' | sed -n '15,25p'", timeout=15)
out = o.read().decode('utf-8', 'ignore').strip()
print("\n=== INIT ERROR HANDLING ===")
print(out)

ssh.close()