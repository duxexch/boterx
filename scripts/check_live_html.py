import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

def run(cmd):
    s, o, e = ssh.exec_command(cmd, timeout=15)
    return o.read().decode('utf-8', 'ignore').strip()

# What does the server-side template say
print("=== base.html x-data on disk ===")
print(run("grep -o 'x-data=\"[^\"]*\"' /opt/bot/dashboard/templates/base.html | head -2"))

print("\n=== version in base.html ===")
print(run("grep -o 'v=20260825[a-z]' /opt/bot/dashboard/templates/base.html | sort -u"))

# What does the live URL serve
print("\n=== live HTML x-data ===")
print(run('curl -s -c /tmp/ck.txt "http://127.0.0.1:8080/vex/admin/admin" -d "admin_id=7146701713&password=Vex-LN36X_SG3bv-UNooqkME" -o /dev/null; curl -s -b /tmp/ck.txt "http://127.0.0.1:8080/dashboard" | grep -o \'x-data="[^"]*"\' | head -2'))

print("\n=== live HTML version ===")
print(run('curl -s -b /tmp/ck.txt "http://127.0.0.1:8080/dashboard" | grep -o \'v=20260825[a-z]\' | sort -u'))

# Check git state on server
print("\n=== server git ===")
print(run("cd /opt/bot && git log --oneline -2"))

# Check service worker registration in base.html
print("\n=== service worker registration? ===")
print(run("grep -rn 'serviceWorker' /opt/bot/dashboard/templates/base.html /opt/bot/dashboard/static/js/app.js /opt/bot/dashboard/static/js/base-app.js 2>/dev/null | head -5"))

ssh.close()