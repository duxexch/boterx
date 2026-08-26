import paramiko, time, sys
sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

def run(cmd, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read()
    err = stderr.read()
    return out.decode('utf-8', 'ignore').strip(), err.decode('utf-8', 'ignore').strip()

print('=== bot_channels.csv (first 5 lines) ===')
out, _ = run('head -5 /opt/bot/bot_channels.csv')
print(out)

print('\n=== bot_channels.csv line count ===')
out, _ = run('wc -l /opt/bot/bot_channels.csv')
print(out)

print('\n=== boterx.db size ===')
out, _ = run('ls -lh /opt/bot/boterx.db')
print(out)

print('\n=== users.csv line count ===')
out, _ = run('wc -l /opt/bot/users.csv 2>/dev/null || echo "missing"')
print(out)

print('\n=== channel_groups.csv line count ===')
out, _ = run('wc -l /opt/bot/channel_groups.csv 2>/dev/null || echo "missing"')
print(out)

print('\n=== .env BOT_TOKEN ===')
out, _ = run('grep BOT_TOKEN /opt/bot/.env 2>/dev/null | head -1')
print(out)

print('\n=== boterx.service status ===')
out, _ = run('systemctl is-active boterx.service')
print(out)

print('\n=== boterx.service log (last 30 lines) ===')
out, _ = run('journalctl -u boterx.service --no-pager -n 30 2>&1', timeout=15)
print(out)

print('\n=== dashboard log (last 15 lines) ===')
out, _ = run('journalctl -u boterx-dashboard.service --no-pager -n 15 2>&1', timeout=15)
print(out)

ssh.close()
