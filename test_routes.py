import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=10)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=30)
    out = stdout.read().decode('utf-8', errors='replace').strip()
    err = stderr.read().decode('utf-8', errors='replace').strip()
    return out, err

# Login
run("""curl -s -c /tmp/r.txt -L -o /dev/null -X POST 'http://localhost:8080/vex/admin/admin' --data-urlencode 'admin_id=7146701713' --data-urlencode 'password=Vex-LN36X_SG3bv-UNooqkME'""")

# Test rental page with auth
out, err = run("curl -s -b /tmp/r.txt 'http://localhost:8080/rental' -w '\\nHTTP_CODE:%{http_code}'")
lines = out.split('\n')
for l in lines[-3:]:
    print(l)
print(f"Size: {len(out)} bytes")

# Check for template errors
stdin, stdout, stderr = ssh.exec_command("journalctl -u boterx-dashboard --no-pager -n 20 2>&1")
logs = stdout.read().decode('utf-8', errors='replace')
print("\n=== Recent logs ===")
print(logs[-1000:] if len(logs) > 1000 else logs)

ssh.close()
