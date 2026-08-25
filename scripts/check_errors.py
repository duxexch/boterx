import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

def run(cmd, timeout=30):
    s, o, e = ssh.exec_command(cmd, timeout=timeout)
    return o.read().decode('utf-8', 'ignore').strip()

logs = run("journalctl -u boterx-dashboard.service --since '5 minutes ago' --no-pager | tail -50")
with open("error_logs.txt", "w", encoding="utf-8") as f:
    f.write(logs)

ssh.close()
print("done")