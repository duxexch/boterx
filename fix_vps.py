import paramiko
import sys

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=15)

commands = [
    "cd /opt/bot && git fetch origin && git reset --hard origin/main",
    "cd /opt/bot && git log --oneline -1",
    "head -1 /opt/bot/dashboard/static/js/app.js",
    "wc -l /opt/bot/dashboard/static/js/app.js",
    "grep -c 'tr(' /opt/bot/dashboard/static/js/app.js",
    "grep -c 'I18N' /opt/bot/dashboard/static/js/app.js",
    "systemctl restart boterx",
    "systemctl restart boterx-dashboard",
    "sleep 2",
    "systemctl status boterx --no-pager | head -3",
    "systemctl status boterx-dashboard --no-pager | head -3",
    "curl -s -k https://127.0.0.1/login -o /dev/null -w '%{http_code}'",
    "curl -s -c /tmp/c5.txt -b /tmp/c5.txt -X POST http://127.0.0.1:8080/login -d 'admin_id=7146701713&password=boterx_admin_2026' -o /dev/null -w '%{http_code}'",
    "curl -s -b /tmp/c5.txt http://127.0.0.1:8080/api/stats | head -5",
    "curl -s -b /tmp/c5.txt http://127.0.0.1:8080/api/wheel-gifts",
]

for cmd in commands:
    sys.stdout.buffer.write(f">>> {cmd[:80]}\n".encode('utf-8'))
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read()
    err = stderr.read()
    if out:
        sys.stdout.buffer.write(out[:500])
        sys.stdout.buffer.write(b"\n")
    if err:
        sys.stdout.buffer.write(b"ERR: ")
        sys.stdout.buffer.write(err[:300])
        sys.stdout.buffer.write(b"\n")
    sys.stdout.buffer.write(b"---\n")
    sys.stdout.buffer.flush()

ssh.close()
sys.stdout.buffer.write(b"DONE\n")
