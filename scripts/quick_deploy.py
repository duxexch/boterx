import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)
ssh.exec_command("cd /opt/bot && git fetch origin && git reset --hard origin/main && systemctl restart boterx-dashboard.service", timeout=60)
import time
time.sleep(25)
for i in range(10):
    s, o, e = ssh.exec_command("curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/health", timeout=10)
    code = o.read().decode('utf-8', 'ignore').strip()
    if code == '200':
        print(f"health OK after {(i+1)*5}s")
        break
    time.sleep(5)
s, o, e = ssh.exec_command("systemctl is-active boterx-dashboard.service boterx.service", timeout=10)
print(o.read().decode('utf-8', 'ignore').strip())
ssh.close()