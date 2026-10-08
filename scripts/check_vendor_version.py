import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

# Test with version param
s, o, e = ssh.exec_command("curl -s -o /dev/null -w '%{http_code}' 'http://127.0.0.1:8080/static/vendor/alpine.min.js?v=20260825a'", timeout=10)
out = o.read().decode('utf-8', 'ignore').strip()
print(f"alpine.min.js?v=20260825a: {out}")

# Test chart
s, o, e = ssh.exec_command("curl -s -o /dev/null -w '%{http_code}' 'http://127.0.0.1:8080/static/vendor/chart.umd.min.js?v=20260825a'", timeout=10)
out = o.read().decode('utf-8', 'ignore').strip()
print(f"chart.umd.min.js?v=20260825a: {out}")

# Test without version
s, o, e = ssh.exec_command("curl -s -o /dev/null -w '%{http_code}' 'http://127.0.0.1:8080/static/vendor/chart.umd.min.js'", timeout=10)
out = o.read().decode('utf-8', 'ignore').strip()
print(f"chart.umd.min.js (no version): {out}")

# Check the actual base.html script tags for vendor files
s, o, e = ssh.exec_command("grep -A2 'chart.umd.min.js' /opt/bot/dashboard/templates/base.html", timeout=10)
out = o.read().decode('utf-8', 'ignore').strip()
print("\nChart script tag:")
print(out)

ssh.close()