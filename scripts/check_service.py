import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

def run(cmd, timeout=30):
    s, o, e = ssh.exec_command(cmd, timeout=timeout)
    return o.read().decode('utf-8', 'ignore').strip()

# Wait for service
for i in range(20):
    out = run("curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/health", timeout=10)
    print(f"Attempt {i+1}: {out}")
    if out == '200':
        break
    time.sleep(5)

# Check logs
logs = run("journalctl -u boterx-dashboard.service --since '5 minutes ago' --no-pager | tail -50")
print("\n=== LOGS ===")
print(logs)

ssh.close()