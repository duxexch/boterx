import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=20)

# Check logs for JavaScript errors
s, o, e = ssh.exec_command("journalctl -u boterx-dashboard.service -n 100 --no-pager | grep -i 'error\\|exception\\|undefined\\|ReferenceError\\|t is not defined\\|notifications is not defined\\|activityTicker is not defined\\|copied is not defined'", timeout=30)
out = o.read().decode('utf-8', 'ignore').strip()

with open('logs_result.txt', 'w', encoding='utf-8') as f:
    f.write(out)

print('Done')
ssh.close()