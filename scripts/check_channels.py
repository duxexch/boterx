import paramiko, time, sys
sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

def run(cmd, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    return stdout.read().decode('utf-8', 'ignore').strip(), stderr.read().decode('utf-8', 'ignore').strip()

print('=== channels API ===')
out, err = run('curl -s -H "X-API-Key: vex_hermes_FkVWYOPLZ230Ru22ib0vRDDKOJL4agfhSBDUuUoMQIM" http://127.0.0.1:8080/api/channels 2>&1 | head -c 500')
print(out[:500])

print('\n=== channel-groups API ===')
out, err = run('curl -s -H "X-API-Key: vex_hermes_FkVWYOPLZ230Ru22ib0vRDDKOJL4agfhSBDUuUoMQIM" http://127.0.0.1:8080/api/channel-groups 2>&1')
print(out[:500])

print('\n=== dashboard log errors (last 30 lines) ===')
out, err = run('journalctl -u boterx-dashboard.service --no-pager -n 30 2>&1', timeout=15)
print(out[-2000:])

print('\n=== bot_channels.csv first 3 lines ===')
out, _ = run('head -3 /opt/bot/bot_channels.csv')
print(out)

ssh.close()
