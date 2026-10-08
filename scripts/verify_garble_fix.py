import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

def run(cmd):
    s, o, e = ssh.exec_command(cmd, timeout=15)
    return o.read().decode('utf-8', 'ignore').strip()

# 1. Confirm window.tr override is GONE from runtime
rt = run("curl -s 'http://127.0.0.1:8080/static/js/i18n-admin-runtime.js?v=20260825c'")
print("runtime contains 'window.tr =':", 'window.tr =' in rt)

# 2. Confirm base-app.js t() uses dict lookup
ba = run("curl -s 'http://127.0.0.1:8080/static/js/base-app.js?v=20260825c'")
print("base-app t() uses tr(key):", 'return tr(key)' in ba)
print("base-app registers Alpine.data:", "Alpine.data('baseApp'" in ba)

# 3. Confirm dashboard serves v=20260825c
dash = run('curl -s -c /tmp/ck.txt "http://127.0.0.1:8080/vex/admin/admin" -d "admin_id=7146701713&password=Vex-LN36X_SG3bv-UNooqkME" -o /dev/null; curl -s -b /tmp/ck.txt "http://127.0.0.1:8080/dashboard"')
print("dashboard uses v=20260825c:", 'v=20260825c' in dash)
print("x-data=baseApp:", 'x-data="baseApp"' in dash)

# 4. Simulate t('dashboard') logic: check I18N dict has the key in app.js
app = run("curl -s 'http://127.0.0.1:8080/static/js/app.js?v=20260825c'")
print("app.js has I18N dict:", 'const I18N' in app)
print("app.js has key-based tr():", 'function tr(key)' in app)
print("app.js tr does dict lookup:", "dict[key] || I18N.ar[key]" in app)

ssh.close()
print("\nDone")