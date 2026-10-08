import paramiko, sys, json
sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

def run(cmd, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    return stdout.read().decode('utf-8', 'ignore').strip(), stderr.read().decode('utf-8', 'ignore').strip()

# Login with redirect follow
run("curl -s -c /tmp/v2.txt 'http://127.0.0.1:8080/vex/admin/admin' -d 'admin_id=7146701713&password=Vex-LN36X_SG3bv-UNooqkME' -L -o /dev/null")

# Get full page
out, _ = run("curl -s -b /tmp/v2.txt 'http://127.0.0.1:8080/vex/admin/admin' -L 2>&1")
print(f"Page length: {len(out)} chars")
print(f"Lines: {out.count(chr(10))}")

# Check for markers
for marker in ['openPostComposer', 'showPostComposer', 'POST COMPOSER', 'Channel Detail', 'channelsApp']:
    count = out.count(marker)
    print(f"  '{marker}': {count}")

# Show first 500 chars to see what's actually rendered
print(f"\n=== First 500 chars ===")
print(out[:500])

# Check if it's a login redirect
if 'login' in out.lower()[:500] or 'admin_id' in out[:500]:
    print("\n!!! PAGE IS LOGIN PAGE - session not working !!!")

ssh.close()
