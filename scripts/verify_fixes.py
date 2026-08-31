import paramiko, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

# Reload nginx
stdin, stdout, stderr = ssh.exec_command("nginx -s reload 2>&1", timeout=10)
print("Nginx reload:", stdout.read().decode("utf-8", "ignore").strip())

# Verify gzip is working
stdin, stdout, stderr = ssh.exec_command("curl -sI -H 'Accept-Encoding: gzip' 'https://vex.deals/static/js/app.js' 2>/dev/null | grep -i 'content-encoding\\|content-length'", timeout=10)
print("Gzip check:", stdout.read().decode("utf-8", "ignore").strip())

# Check new gunicorn workers
stdin, stdout, stderr = ssh.exec_command("ps aux | grep gunicorn | grep -v grep", timeout=10)
print("Workers:", stdout.read().decode("utf-8", "ignore").strip())

ssh.close()
