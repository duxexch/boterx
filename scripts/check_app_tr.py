import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

# Get the full app.js tr() function
s, o, e = ssh.exec_command("curl -s 'http://127.0.0.1:8080/static/js/app.js?v=20260825a' | sed -n '480,510p'", timeout=15)
out = o.read().decode('utf-8', 'ignore').strip()
print("=== app.js tr() function ===")
print(out)

# Test if I18N is in app.js
s, o, e = ssh.exec_command("curl -s 'http://127.0.0.1:8080/static/js/app.js?v=20260825a' | head -10", timeout=15)
out = o.read().decode('utf-8', 'ignore').strip()
print("\n=== app.js I18N ===")
print(out)

ssh.close()