import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

print("stop/pull/start...")
ssh.exec_command("systemctl stop boterx-dashboard.service", timeout=30)
time.sleep(3)
s, o, e = ssh.exec_command("cd /opt/bot && git fetch origin && git reset --hard origin/main", timeout=60)
print(o.read().decode('utf-8', 'ignore').strip())
ssh.exec_command("systemctl start boterx-dashboard.service", timeout=30)

# wait for health with retries
for i in range(12):
    time.sleep(5)
    s, o, e = ssh.exec_command("curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/health", timeout=10)
    code = o.read().decode('utf-8', 'ignore').strip()
    print(f"attempt {i+1}: {code}")
    if code == '200':
        break

s, o, e = ssh.exec_command("systemctl is-active boterx-dashboard.service boterx.service", timeout=10)
print(o.read().decode('utf-8', 'ignore').strip())
ssh.close()
print("deploy done")