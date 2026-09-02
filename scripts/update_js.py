import paramiko, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

# Read the current JS section
stdin, stdout, stderr = ssh.exec_command("sed -n '1180,1245p' /opt/bot/dashboard/templates/landing.html", timeout=10)
print(stdout.read().decode('utf-8', 'ignore'))

ssh.close()