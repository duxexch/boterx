import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=20)

s, o, e = ssh.exec_command('cat /opt/bot/.env 2>/dev/null | grep -E "ADMIN|DASHBOARD"', timeout=10)
out = o.read().decode('utf-8', 'ignore').strip()

with open('env_result.txt', 'w', encoding='utf-8') as f:
    f.write(out)

print('Done')
ssh.close()