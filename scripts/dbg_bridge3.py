import paramiko, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

stdin, stdout, stderr = ssh.exec_command("cat /opt/bot/companies.csv", timeout=10)
print(stdout.read().decode('utf-8','ignore'))

stdin, stdout, stderr = ssh.exec_command("curl -sk -L 'https://vex.deals/c/1' 2>/dev/null | head -20", timeout=10)
print(stdout.read().decode('utf-8','ignore')[:1000])

# Check what route handles /c/1
stdin, stdout, stderr = ssh.exec_command("grep -n \"c/<\" /opt/bot/dashboard/app.py", timeout=10)
print(stdout.read().decode('utf-8','ignore'))

ssh.close()
