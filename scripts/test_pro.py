import paramiko, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

import time
# Test bridge topbar pro
stdin, stdout, stderr = ssh.exec_command("curl -sk 'https://vex.deals/go/1' 2>/dev/null | grep -c 'bridge-topbar'", timeout=10)
print("topbar:", stdout.read().decode('utf-8','ignore').strip())
stdin, stdout, stderr = ssh.exec_command("curl -sk 'https://vex.deals/go/1' 2>/dev/null | grep -c 'depositSheet\\|transferSheet\\|withdrawSheet'", timeout=10)
print("sheets:", stdout.read().decode('utf-8','ignore').strip())
stdin, stdout, stderr = ssh.exec_command("curl -sk 'https://vex.deals/go/1' 2>/dev/null | grep -c 'skeleton'", timeout=10)
print("skeleton:", stdout.read().decode('utf-8','ignore').strip())

# Test performance
stdin, stdout, stderr = ssh.exec_command("curl -sk -o /dev/null -w 'TTFB:%{time_starttransfer} Total:%{time_total}' 'https://vex.deals/go/1' 2>/dev/null", timeout=10)
print(stdout.read().decode('utf-8','ignore').strip())

# Test gzip
stdin, stdout, stderr = ssh.exec_command("curl -sI -H 'Accept-Encoding: gzip' 'https://vex.deals/go/1' 2>/dev/null | grep -i content-encoding", timeout=10)
print("gzip bridge:", stdout.read().decode('utf-8','ignore').strip())

ssh.close()
