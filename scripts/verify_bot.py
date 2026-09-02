import paramiko, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

stdin, stdout, stderr = ssh.exec_command("grep -A2 'bridge_url' /opt/bot/comprehensive_bot.py | head -20", timeout=10)
print(stdout.read().decode('utf-8','ignore'))

stdin, stdout, stderr = ssh.exec_command("grep -n 'go/' /opt/bot/comprehensive_bot.py | head -10", timeout=10)
print(stdout.read().decode('utf-8','ignore'))

stdin, stdout, stderr = ssh.exec_command("grep -n 'app.*go/' /opt/bot/dashboard/app.py | head -10", timeout=10)
print(stdout.read().decode('utf-8','ignore'))

ssh.close()
