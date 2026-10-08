import urllib.request
import paramiko

# Download latest Alpine.js (3.14.x)
url = "https://cdn.jsdelivr.net/npm/alpinejs@3.14.2/dist/cdn.min.js"
print("Downloading Alpine.js 3.14.2...")
response = urllib.request.urlopen(url)
alpine_js = response.read()

# Save locally
with open("alpine.min.js", "wb") as f:
    f.write(alpine_js)
print(f"Downloaded {len(alpine_js)} bytes")

# Upload to server
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

sftp = ssh.open_sftp()
sftp.put("alpine.min.js", "/opt/bot/dashboard/static/vendor/alpine.min.js")
sftp.close()

# Also update the version in base.html to bust cache
run = lambda cmd: ssh.exec_command(cmd, timeout=30)[1].read().decode('utf-8', 'ignore').strip()
run("sed -i 's/alpine.min.js\"/alpine.min.js?v=3.14.2\"/g' /opt/bot/dashboard/templates/base.html")

# Restart service
ssh.exec_command("systemctl restart boterx-dashboard.service", timeout=60)
import time
time.sleep(10)

# Verify
code = run("curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/health")
print(f"Health: {code}")

ssh.close()
print("Alpine updated!")