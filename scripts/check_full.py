import paramiko, sys
sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

def run(cmd, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    return stdout.read().decode('utf-8', 'ignore').strip(), stderr.read().decode('utf-8', 'ignore').strip()

print('=== ADMIN_USER_IDS ===')
out, _ = run('grep ADMIN_USER_IDS /opt/bot/.env 2>/dev/null || echo "NOT SET"')
print(out)

print('\n=== ADMIN_PASSWORD ===')
out, _ = run('grep ADMIN_PASSWORD /opt/bot/.env 2>/dev/null || echo "NOT SET"')
print(out)

print('\n=== All env vars ===')
out, _ = run('cat /opt/bot/.env')
print(out)

print('\n=== Login test with curl (follow redirects, cookie jar) ===')
out, _ = run("curl -v -s -c /tmp/c2.txt -b /tmp/c2.txt 'http://127.0.0.1:8080/vex/admin/admin' -d 'admin_id=7146701713&password=Vex-LN36X_SG3bv-UNooqkME' -L -w '\\nHTTP:%{http_code}' 2>&1 | tail -20")
print(out)

print('\n=== Session cookie ===')
out, _ = run('cat /tmp/c2.txt')
print(out)

print('\n=== Channels with login session ===')
out, _ = run("curl -s -b /tmp/c2.txt http://127.0.0.1:8080/api/channels 2>&1 | head -c 300")
print(out)

ssh.close()
