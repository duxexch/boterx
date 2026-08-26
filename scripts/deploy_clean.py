import paramiko, time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

print('1. Stopping services...')
stdin, stdout, stderr = ssh.exec_command('systemctl stop boterx-dashboard.service boterx.service', timeout=60)
stdout.channel.recv_exit_status()
time.sleep(3)

print('2. Pulling latest code...')
stdin, stdout, stderr = ssh.exec_command('cd /opt/bot && git fetch origin && git reset --hard origin/main && git clean -fd', timeout=120)
out = stdout.read().decode('utf-8', 'ignore').strip()
print(out)
err = stderr.read().decode('utf-8', 'ignore').strip()
if err:
    print('STDERR:', err)

print('3. Starting dashboard...')
stdin, stdout, stderr = ssh.exec_command('systemctl start boterx-dashboard.service', timeout=60)
stdout.channel.recv_exit_status()
time.sleep(5)

print('4. Starting bot...')
stdin, stdout, stderr = ssh.exec_command('systemctl start boterx.service', timeout=60)
stdout.channel.recv_exit_status()
time.sleep(5)

print('5. Health check...')
for i in range(15):
    time.sleep(5)
    stdin, stdout, stderr = ssh.exec_command('curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/health', timeout=15)
    code = stdout.read().decode('utf-8', 'ignore').strip()
    print(f'  attempt {i+1}: {code}')
    if code == '200':
        break

print('6. Service status...')
stdin, stdout, stderr = ssh.exec_command('systemctl is-active boterx-dashboard.service boterx.service', timeout=15)
print(stdout.read().decode('utf-8', 'ignore').strip())

ssh.close()
print('DONE')
