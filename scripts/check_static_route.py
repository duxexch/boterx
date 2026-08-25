import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

# Test different paths
paths = [
    "/static/vendor/alpine.min.js",
    "/static/js/alpine.min.js",
    "/vendor/alpine.min.js",
]

for path in paths:
    s, o, e = ssh.exec_command(f"curl -s -o /dev/null -w '%{{http_code}}' 'http://127.0.0.1:8080{path}'", timeout=10)
    out = o.read().decode('utf-8', 'ignore').strip()
    print(f"{path}: {out}")

# Check Flask static folder config
s, o, e = ssh.exec_command("grep -n 'static_folder\\|static_url_path' /opt/bot/dashboard/app.py | head -10", timeout=10)
out = o.read().decode('utf-8', 'ignore').strip()
print("\nStatic config:")
print(out)

# Check if there's a custom static route
s, o, e = ssh.exec_command("grep -n 'static' /opt/bot/dashboard/app.py | head -30", timeout=10)
out = o.read().decode('utf-8', 'ignore').strip()
print("\nStatic routes:")
print(out)

ssh.close()