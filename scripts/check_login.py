import paramiko, time, sys
sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

def run(cmd, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    return stdout.read().decode('utf-8', 'ignore').strip(), stderr.read().decode('utf-8', 'ignore').strip()

# Step 1: Login via form post (like browser)
print('=== Step 1: Login ===')
out, _ = run("curl -s -c /tmp/cookies.txt -L -X POST 'http://127.0.0.1:8080/vex/admin/admin' -d 'admin_id=7146701713&password=Vex-LN36X_SG3bv-UNooqkME' -w '\\nHTTP_CODE:%{http_code}' 2>&1 | tail -5")
print(out)

# Step 2: Get channels with session
print('\n=== Step 2: Get channels with login session ===')
out, _ = run("curl -s -b /tmp/cookies.txt http://127.0.0.1:8080/api/channels 2>&1 | head -c 500")
print(out)

# Step 3: Check session content
print('\n=== Step 3: Cookie content ===')
out, _ = run("cat /tmp/cookies.txt")
print(out)

ssh.close()
