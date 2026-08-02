import paramiko
import sys

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=15)

# Force pull — the "Already up to date" means /opt/bot might have local changes blocking the pull
commands = [
    "cd /opt/bot && git fetch origin",
    "cd /opt/bot && git reset --hard origin/main",
    "cd /opt/bot && git log --oneline -3",
    "head -1 /opt/bot/dashboard/static/js/app.js",
    "wc -l /opt/bot/dashboard/static/js/app.js",
    "systemctl restart boterx-dashboard",
    "systemctl restart boterx",
    "sleep 2",
    "systemctl status boterx-dashboard --no-pager | head -3",
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
