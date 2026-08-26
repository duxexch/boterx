import paramiko, sys, json
sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

def run(cmd, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    return stdout.read().decode('utf-8', 'ignore').strip(), stderr.read().decode('utf-8', 'ignore').strip()

run("rm -f /tmp/v4.txt")
# Login (redirects to /dashboard)
run("curl -s -c /tmp/v4.txt 'http://127.0.0.1:8080/vex/admin/admin' -d 'admin_id=7146701713&password=Vex-LN36X_SG3bv-UNooqkME' -L -o /dev/null")

# Access /dashboard (which is the channels page after login)
out, _ = run("curl -s -b /tmp/v4.txt 'http://127.0.0.1:8080/dashboard' | wc -l")
print(f"Dashboard lines: {out}")

out, _ = run("curl -s -b /tmp/v4.txt 'http://127.0.0.1:8080/dashboard'")
for marker in ['openPostComposer', 'showPostComposer', 'POST COMPOSER', 'Channel Detail', 'channelsApp']:
    count = out.count(marker)
    print(f"  '{marker}': {count}")

print(f"\nTotal page chars: {len(out)}")

# Also check which route serves channels page
out2, _ = run("grep -n 'channels\|channel_groups\|admin/admin' /opt/bot/dashboard/app.py | grep 'route' | head -20")
print(f"\nChannel routes:\n{out2}")

ssh.close()
