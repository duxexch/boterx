import paramiko, time, sys
sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

def run(cmd, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    return stdout.read().decode('utf-8', 'ignore').strip(), stderr.read().decode('utf-8', 'ignore').strip()

# Check _is_super_admin_session for admin_id=7146701713
print('=== RBAC role for admin 7146701713 ===')
out, _ = run("python3 -c \"import sqlite3; conn=sqlite3.connect('/opt/bot/boterx.db'); c=conn.execute('SELECT * FROM admin_roles WHERE admin_id=?', ('7146701713',)); print(c.fetchall())\" 2>&1")
print(out)

print('\n=== all tables in boterx.db ===')
out, _ = run("python3 -c \"import sqlite3; conn=sqlite3.connect('/opt/bot/boterx.db'); c=conn.execute(\\\"SELECT name FROM sqlite_master WHERE type='table'\\\"); print([r[0] for r in c.fetchall()])\" 2>&1")
print(out)

print('\n=== admin_roles table ===')
out, _ = run("python3 -c \"import sqlite3; conn=sqlite3.connect('/opt/bot/boterx.db'); c=conn.execute('SELECT * FROM admin_roles'); print(c.fetchall())\" 2>&1")
print(out)

print('\n=== login as admin and check channels ===')
out, _ = run("curl -s -c /tmp/c.txt -b /tmp/c.txt -X POST http://127.0.0.1:8080/api/login -H 'Content-Type: application/json' -d '{\"admin_id\":\"7146701713\",\"password\":\"Vex-LN36X_SG3bv-UNooqkME\"}' | head -c 200")
print(out)

print('\n=== channels with login session ===')
out, _ = run("curl -s -c /tmp/c.txt -b /tmp/c.txt http://127.0.0.1:8080/api/channels | head -c 500")
print(out)

ssh.close()
