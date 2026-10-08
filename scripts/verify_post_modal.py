import paramiko, sys
sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

def run(cmd, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    return stdout.read().decode('utf-8', 'ignore').strip(), stderr.read().decode('utf-8', 'ignore').strip()

# Login
run("curl -s -c /tmp/v.txt 'http://127.0.0.1:8080/vex/admin/admin' -d 'admin_id=7146701713&password=Vex-LN36X_SG3bv-UNooqkME' -o /dev/null")

# Check that the HTML page contains the modal
print("=== Page contains post composer modal ===")
out, _ = run("curl -s -b /tmp/v.txt http://127.0.0.1:8080/vex/admin/admin 2>&1 | grep -c 'showPostComposer'")
print(f"  showPostComposer references: {out}")

out, _ = run("curl -s -b /tmp/v.txt http://127.0.0.1:8080/vex/admin/admin 2>&1 | grep -c 'openPostComposer'")
print(f"  openPostComposer references: {out}")

out, _ = run("curl -s -b /tmp/v.txt http://127.0.0.1:8080/vex/admin/admin 2>&1 | grep -c 'POST COMPOSER MODAL'")
print(f"  POST COMPOSER MODAL comment: {out}")

out, _ = run("curl -s -b /tmp/v.txt http://127.0.0.1:8080/vex/admin/admin 2>&1 | grep -c 'Channel Detail Modal'")
print(f"  Channel Detail Modal comment: {out}")

# Check channels API
print("\n=== Channels API ===")
out, _ = run("curl -s -b /tmp/v.txt http://127.0.0.1:8080/api/channels 2>&1")
import json
try:
    d = json.loads(out)
    print(f"  channels: {len(d.get('channels', []))}")
except:
    print(f"  Error: {out[:200]}")

# Check JS syntax
print("\n=== JS Syntax ===")
out, _ = run("node --check /opt/bot/dashboard/static/js/app.js 2>&1")
print(f"  app.js: {out or 'OK'}")
out, _ = run("node --check /opt/bot/dashboard/static/js/admin-phrases.js 2>&1")
print(f"  admin-phrases.js: {out or 'OK'}")

# Check services
print("\n=== Services ===")
out, _ = run("systemctl is-active boterx.service boterx-dashboard.service")
print(f"  {out}")

ssh.close()
