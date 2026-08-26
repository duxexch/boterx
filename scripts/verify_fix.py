import paramiko, sys
sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

def run(cmd, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    return stdout.read().decode('utf-8', 'ignore').strip(), stderr.read().decode('utf-8', 'ignore').strip()

print('=== app.js syntax ===')
out, _ = run("node --check /opt/bot/dashboard/static/js/app.js 2>&1")
print(out or "OK")

print('=== admin-phrases.js syntax ===')
out, _ = run("node --check /opt/bot/dashboard/static/js/admin-phrases.js 2>&1")
print(out or "OK")

print('=== Bot status ===')
out, _ = run("systemctl is-active boterx.service boterx-dashboard.service")
print(out)

print('=== Channels API (with login) ===')
run("curl -s -c /tmp/v.txt 'http://127.0.0.1:8080/vex/admin/admin' -d 'admin_id=7146701713&password=Vex-LN36X_SG3bv-UNooqkME' -o /dev/null")
out, _ = run("curl -s -b /tmp/v.txt http://127.0.0.1:8080/api/channels 2>&1")
import json
try:
    d = json.loads(out)
    print(f"channels: {len(d.get('channels', []))}")
except:
    print(out[:200])

ssh.close()
