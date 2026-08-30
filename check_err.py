import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=10)

stdin, stdout, stderr = ssh.exec_command("journalctl -u boterx-dashboard --no-pager -n 60 2>&1 | grep -i 'error\\|traceback\\|exception' | tail -30")
out = stdout.read().decode('utf-8', errors='replace')
with open('err.txt', 'w', encoding='utf-8') as f:
    f.write(out)
print(out[:3000] if out else 'No errors')

ssh.close()
