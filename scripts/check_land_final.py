import paramiko, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

# Check main landing page
stdin, stdout, stderr = ssh.exec_command("curl -sk 'https://vex.deals/' 2>/dev/null | head -20", timeout=10)
print(stdout.read().decode('utf-8','ignore')[:2000])

# Check health
stdin, stdout, stderr = ssh.exec_command("curl -sk -o /dev/null -w 'home: %{http_code}' 'https://vex.deals/' 2>/dev/null", timeout=10)
print("Status:", stdout.read().decode('utf-8','ignore').strip())

# Check logs for errors
stdin, stdout, stderr = ssh.exec_command("journalctl -u boterx-dashboard --since '2 min ago' --no-pager 2>/dev/null | tail -30", timeout=10)
print(stdout.read().decode('utf-8','ignore'))

ssh.close()