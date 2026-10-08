import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=10)
cmds = [
    'sqlite3 /opt/bot/boterx.db "SELECT uid, role, permissions FROM admin_roles;"',
    'curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/admins',
    'curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/dashboard',
    'curl -s -o /dev/null -w "%{http_code}" -H "Cookie: session=test" http://localhost:8080/admins',
]
for cmd in cmds:
    print(f"\n>>> {cmd}")
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if out: print(f"  OUT: {out}")
    if err: print(f"  ERR: {err}")
ssh.close()
