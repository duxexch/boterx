import paramiko, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

import time
stdin, stdout, stderr = ssh.exec_command("curl -sk 'https://vex.deals/go/1' 2>/dev/null | head -20", timeout=10)
print(stdout.read().decode('utf-8','ignore')[:1000])

stdin, stdout, stderr = ssh.exec_command("curl -sk -o /dev/null -w 'go/1: %{http_code}' 'https://vex.deals/go/1' 2>/dev/null", timeout=10)
print(stdout.read().decode('utf-8','ignore'))

stdin, stdout, stderr = ssh.exec_command("curl -sk -o /dev/null -w 'c/1: %{http_code}' 'https://vex.deals/c/1' 2>/dev/null", timeout=10)
print(stdout.read().decode('utf-8','ignore'))

# Test admin page
stdin, stdout, stderr = ssh.exec_command("curl -sk -c /tmp/br3.txt -X POST 'https://vex.deals/vex/admin/admin' -H 'Content-Type: application/x-www-form-urlencoded' -d 'admin_id=7146701713&password=Vex-LN36X_SG3bv-UNooqkME' -o /dev/null -w '%{http_code}'", timeout=10)
print("login", stdout.read().decode('utf-8','ignore'))
time.sleep(1)
stdin, stdout, stderr = ssh.exec_command("curl -sk -b /tmp/br3.txt 'https://vex.deals/company-transfers' -o /dev/null -w 'company-transfers: %{http_code}'", timeout=10)
print(stdout.read().decode('utf-8','ignore'))

stdin, stdout, stderr = ssh.exec_command("curl -sk -b /tmp/br3.txt 'https://vex.deals/api/admin/company-transfers' 2>/dev/null | head -c 200", timeout=10)
print(stdout.read().decode('utf-8','ignore'))

ssh.close()
