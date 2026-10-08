import paramiko, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

stdin, stdout, stderr = ssh.exec_command('curl -sk "https://vex.deals/" 2>/dev/null | head -150', timeout=10)
content = stdout.read().decode('utf-8', 'ignore')
print(content[:3000])

ssh.close()