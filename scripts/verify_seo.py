import paramiko, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

stdin, stdout, stderr = ssh.exec_command('curl -sk "https://vex.deals/sitemap.xml" 2>/dev/null | head -15', timeout=10)
print('=== SITEMAP ===')
print(stdout.read().decode('utf-8','ignore'))

stdin, stdout, stderr = ssh.exec_command('curl -sk "https://vex.deals/robots.txt" 2>/dev/null', timeout=10)
print('=== ROBOTS ===')
print(stdout.read().decode('utf-8','ignore'))

ssh.close()