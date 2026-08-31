import paramiko, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

# Replace the commented gzip_types line using Python on server
cmd = """python3 -c "
import re
with open('/etc/nginx/nginx.conf', 'r') as f:
    content = f.read()

# Replace the commented gzip_types line
old = '# gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;'
new = 'gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript image/svg+xml;'
content = content.replace(old, new)

with open('/etc/nginx/nginx.conf', 'w') as f:
    f.write(content)
print('Fixed!')
" """
stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
print("Fix result:", stdout.read().decode("utf-8", "ignore").strip())
err = stderr.read().decode("utf-8", "ignore").strip()
if err:
    print("STDERR:", err)

# Verify
stdin, stdout, stderr = ssh.exec_command("grep -n 'gzip_types' /etc/nginx/nginx.conf", timeout=10)
print("gzip_types line:", stdout.read().decode("utf-8", "ignore").strip())

# Test nginx config
stdin, stdout, stderr = ssh.exec_command("nginx -t 2>&1", timeout=10)
print("Nginx test:", stdout.read().decode("utf-8", "ignore").strip())

# Reload
stdin, stdout, stderr = ssh.exec_command("nginx -s reload 2>&1", timeout=10)
print("Nginx reload:", stdout.read().decode("utf-8", "ignore").strip())

# Test gzip
import time; time.sleep(1)
stdin, stdout, stderr = ssh.exec_command("curl -sI -H 'Accept-Encoding: gzip' 'https://vex.deals/static/js/app.js' 2>/dev/null | head -15", timeout=10)
print("Gzip response:", stdout.read().decode("utf-8", "ignore").strip())

ssh.close()
