import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

def run(cmd, timeout=30):
    s, o, e = ssh.exec_command(cmd, timeout=timeout)
    out = o.read().decode('utf-8', 'ignore').strip()
    err = e.read().decode('utf-8', 'ignore').strip()
    return out, err

# Login
run('curl -s -c /tmp/ck.txt "http://127.0.0.1:8080/vex/admin/admin" -d "admin_id=7146701713&password=Vex-LN36X_SG3bv-UNooqkME" -o /dev/null')

# 1. What does /api/channels return?
api_out, _ = run('curl -s -b /tmp/ck.txt -w "\\nHTTP:%{http_code}" http://127.0.0.1:8080/api/channels')
with open("api_channels.txt", "w", encoding="utf-8") as f:
    f.write(api_out)

# 2. What data files exist for channels?
files, _ = run("ls -la /opt/bot/*.csv /opt/bot/data/*.csv 2>/dev/null | grep -i channel; ls -la /opt/bot/boterx.db 2>/dev/null")
with open("channel_files.txt", "w", encoding="utf-8") as f:
    f.write(files)

# 3. Server logs for /api/channels errors
logs, _ = run("journalctl -u boterx-dashboard.service --since '30 minutes ago' --no-pager | grep -i -A8 'channels' | head -60")
with open("channels_logs.txt", "w", encoding="utf-8") as f:
    f.write(logs)

print("done")
ssh.close()