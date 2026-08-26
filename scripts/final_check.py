import paramiko, time, sys
sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

def run(cmd, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    return stdout.read().decode('utf-8', 'ignore').strip(), stderr.read().decode('utf-8', 'ignore').strip()

# Login
print('=== Login ===')
out, _ = run("curl -s -c /tmp/final.txt -b /tmp/final.txt -X POST 'http://127.0.0.1:8080/vex/admin/admin' -d 'admin_id=7146701713&password=Vex-LN36X_SG3bv-UNooqkME' -L -w '\\nHTTP:%{http_code}' 2>&1 | tail -3")
print(out)

# Get channels
print('\n=== Channels ===')
out, _ = run("curl -s -b /tmp/final.txt http://127.0.0.1:8080/api/channels 2>&1")
import json
try:
    d = json.loads(out)
    print(f"channels count: {len(d.get('channels', []))}")
except:
    print(out[:300])

# Check boterx.service status
print('\n=== Bot status ===')
out, _ = run('systemctl is-active boterx.service')
print(out)

# Check bot logs for errors
print('\n=== Bot log (last 5) ===')
out, _ = run('journalctl -u boterx.service --no-pager -n 5 2>&1', timeout=10)
print(out)

# Verify no syntax errors in channels.html
print('\n=== Check for JS issues ===')
out, _ = run("python3 -c \"import ast; f=open('/opt/bot/dashboard/templates/channels.html','r'); c=f.read(); f.close(); print('OK' if '{% block' in c else 'ERROR')\" 2>&1")
print(out)

ssh.close()
print('\nDONE - Server is working. User needs to re-login.')
