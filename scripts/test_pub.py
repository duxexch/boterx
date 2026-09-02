import paramiko, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

import time
# login
stdin, stdout, stderr = ssh.exec_command("curl -sk -c /tmp/pub.txt -X POST 'https://vex.deals/vex/admin/admin' -H 'Content-Type: application/x-www-form-urlencoded' -d 'admin_id=7146701713&password=Vex-LN36X_SG3bv-UNooqkME' -o /dev/null -w '%{http_code}'", timeout=10)
print("login", stdout.read().decode('utf-8','ignore'))
time.sleep(1)

# status
stdin, stdout, stderr = ssh.exec_command("curl -sk -b /tmp/pub.txt 'https://vex.deals/api/publishing/status' 2>/dev/null", timeout=10)
print("status", stdout.read().decode('utf-8','ignore'))

# toggle off
stdin, stdout, stderr = ssh.exec_command("curl -sk -b /tmp/pub.txt -X POST 'https://vex.deals/api/publishing/toggle' -H 'Content-Type: application/json' -d '{\"enabled\":false}' 2>/dev/null", timeout=10)
print("toggle off", stdout.read().decode('utf-8','ignore'))

# try to publish (should be blocked)
stdin, stdout, stderr = ssh.exec_command("curl -sk -b /tmp/pub.txt -X POST 'https://vex.deals/api/broadcast' -H 'Content-Type: application/json' -d '{}' -w ' HTTP:%{http_code}' 2>/dev/null", timeout=10)
print("broadcast when disabled", stdout.read().decode('utf-8','ignore')[:200])

# toggle on
stdin, stdout, stderr = ssh.exec_command("curl -sk -b /tmp/pub.txt -X POST 'https://vex.deals/api/publishing/toggle' -H 'Content-Type: application/json' -d '{\"enabled\":true}' 2>/dev/null", timeout=10)
print("toggle on", stdout.read().decode('utf-8','ignore'))

# check button in html
stdin, stdout, stderr = ssh.exec_command("curl -sk -b /tmp/pub.txt 'https://vex.deals/dashboard' 2>/dev/null | grep -c 'publishingEnabled'", timeout=10)
print("button in html", stdout.read().decode('utf-8','ignore').strip())

ssh.close()
