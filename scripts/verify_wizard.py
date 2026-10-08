import paramiko, sys
sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

def run(cmd, timeout=60):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    return stdout.read().decode('utf-8', 'ignore').strip()

run("rm -f /tmp/v6.txt")
run("curl -s -c /tmp/v6.txt 'http://127.0.0.1:8080/vex/admin/admin' -d 'admin_id=7146701713&password=Vex-LN36X_SG3bv-UNooqkME' -L -o /dev/null")

out = run("curl -s -b /tmp/v6.txt 'http://127.0.0.1:8080/channels'")
markers = ['POST COMPOSER WIZARD', 'showPostComposer', 'postStep', 'postSearch', 'openPostComposer', 'Channel Detail Modal']
for m in markers:
    print(f"  '{m}': {out.count(m)}")
print(f"  Total length: {len(out)} chars")

# Check services
out2 = run("systemctl is-active boterx.service boterx-dashboard.service")
print(f"\n  Services: {out2}")

ssh.close()
