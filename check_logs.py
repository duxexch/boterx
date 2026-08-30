import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=10)

# Check gunicorn error log
stdin, stdout, stderr = ssh.exec_command("journalctl -u boterx-dashboard --no-pager -n 100 2>&1 | grep -i 'error\\|traceback\\|exception' | tail -30")
out = stdout.read().decode('utf-8', errors='replace')
with open('errors.txt', 'w', encoding='utf-8') as f:
    f.write(out)
print(out[:2000] if out else 'No errors found')

ssh.close()
