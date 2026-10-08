import paramiko, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

# Check bot service config
stdin, stdout, stderr = ssh.exec_command("cat /etc/systemd/system/boterx.service 2>/dev/null", timeout=10)
print("=== BOT SERVICE ===")
print(stdout.read().decode('utf-8','ignore'))

# Check bot process
stdin, stdout, stderr = ssh.exec_command("ps aux | grep -E 'bot|python' | grep -v grep", timeout=10)
print("\n=== PROCESSES ===")
print(stdout.read().decode('utf-8','ignore'))

# Check VPS load
stdin, stdout, stderr = ssh.exec_command("uptime; free -h; df -h | head -5; cat /proc/loadavg", timeout=10)
print("\n=== VPS LOAD ===")
print(stdout.read().decode('utf-8','ignore'))

# Check bot logs for delays
stdin, stdout, stderr = ssh.exec_command("journalctl -u boterx --since '5 min ago' --no-pager 2>/dev/null | tail -20", timeout=10)
print("\n=== BOT LOGS ===")
print(stdout.read().decode('utf-8','ignore')[:2000])

# Check polling interval in bot code
stdin, stdout, stderr = ssh.exec_command("grep -n 'getUpdates\\|polling\\|timeout\\|sleep' /opt/bot/comprehensive_bot.py | head -20", timeout=10)
print("\n=== BOT POLLING ===")
print(stdout.read().decode('utf-8','ignore'))

# Check if bot does sync file reads on every message
stdin, stdout, stderr = ssh.exec_command("grep -n 'read_csv\\|open.*csv\\|find_user' /opt/bot/comprehensive_bot.py | head -20", timeout=10)
print("\n=== FILE READS ===")
print(stdout.read().decode('utf-8','ignore'))

ssh.close()
