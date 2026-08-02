import paramiko
import sys

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=15)

# Fix nginx static path + add DASHBOARD_PASSWORD to .env
commands = [
    # Fix nginx static path from /root/bot to /opt/bot
    "sed -i 's|/root/bot/dashboard/static/|/opt/bot/dashboard/static/|g' /etc/nginx/sites-enabled/boterx-dashboard",
    "sed -i 's|/root/bot/dashboard/static/|/opt/bot/dashboard/static/|g' /etc/nginx/sites-available/boterx-dashboard",
    # Add DASHBOARD_PASSWORD to .env if missing
    "grep -q DASHBOARD_PASSWORD /opt/bot/.env || echo 'DASHBOARD_PASSWORD=boterx_admin_2026' >> /opt/bot/.env",
    "grep -q DASHBOARD_PORT /opt/bot/.env || echo 'DASHBOARD_PORT=8080' >> /opt/bot/.env",
    "grep -q DASHBOARD_HOST /opt/bot/.env || echo 'DASHBOARD_HOST=0.0.0.0' >> /opt/bot/.env",
    # Restart everything
    "nginx -t",
    "systemctl restart nginx",
    "systemctl restart boterx-dashboard",
    "systemctl restart boterx",
    "sleep 3",
    # Verify
    "systemctl status boterx-dashboard --no-pager | head -3",
    "systemctl status boterx --no-pager | head -3",
    "curl -s -c /tmp/c2.txt -b /tmp/c2.txt -X POST http://127.0.0.1:8080/login -d 'admin_id=7146701713&password=boterx_admin_2026' -o /dev/null -w '%{http_code}'",
    "curl -s -b /tmp/c2.txt http://127.0.0.1:8080/api/stats | head -5",
    "cat /etc/nginx/sites-enabled/boterx-dashboard | grep static",
    # Test from outside
    "curl -s -k https://127.0.0.1/login -o /dev/null -w '%{http_code}'",
]

for cmd in commands:
    sys.stdout.buffer.write(f">>> {cmd}\n".encode('utf-8'))
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
