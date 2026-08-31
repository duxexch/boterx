import paramiko, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

# Show the gzip section of nginx.conf
stdin, stdout, stderr = ssh.exec_command("grep -A 15 'gzip on' /etc/nginx/nginx.conf", timeout=10)
print("=== nginx gzip section ===")
print(stdout.read().decode("utf-8", "ignore"))

# The issue: gzip is on but the server block might override it or nginx might need restart (not just reload)
stdin, stdout, stderr = ssh.exec_command("systemctl restart nginx 2>&1", timeout=10)
print("Nginx restart:", stdout.read().decode("utf-8", "ignore").strip())

# Test again
import time; time.sleep(2)
stdin, stdout, stderr = ssh.exec_command("curl -sI -H 'Accept-Encoding: gzip' 'https://vex.deals/static/js/app.js' 2>/dev/null | head -20", timeout=10)
print("Gzip check after restart:", stdout.read().decode("utf-8", "ignore").strip())

ssh.close()
