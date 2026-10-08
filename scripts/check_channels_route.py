import paramiko, sys, json
sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

def run(cmd, timeout=60):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    return stdout.read().decode('utf-8', 'ignore').strip(), stderr.read().decode('utf-8', 'ignore').strip()

run("rm -f /tmp/v5.txt")
run("curl -s -c /tmp/v5.txt 'http://127.0.0.1:8080/vex/admin/admin' -d 'admin_id=7146701713&password=Vex-LN36X_SG3bv-UNooqkME' -L -o /dev/null")

# Access /channels
out, _ = run("curl -s -b /tmp/v5.txt 'http://127.0.0.1:8080/channels' | wc -l")
print(f"/channels lines: {out}")

out, _ = run("curl -s -b /tmp/v5.txt 'http://127.0.0.1:8080/channels'")
for marker in ['openPostComposer', 'showPostComposer', 'POST COMPOSER', 'Channel Detail', 'channelsApp', '{% block']:
    count = out.count(marker)
    print(f"  '{marker}': {count}")

# Also check the first 300 chars
print(f"\nFirst 300 chars:")
print(out[:300])

ssh.close()
