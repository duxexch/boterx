import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

# Test all JS files with new version
js_files = [
    "/static/vendor/chart.umd.min.js",
    "/static/vendor/alpine.min.js?v=20260825b",
    "/static/js/app.js?v=20260825b",
    "/static/js/i18n-admin-lexicon.js?v=20260825b",
    "/static/js/i18n-admin-runtime.js?v=20260825b",
    "/static/js/base-app.js?v=20260825b",
]

for js in js_files:
    cmd = "curl -s -o /dev/null -w 'http_code:%{http_code} size:%{size_download}' 'http://127.0.0.1:8080" + js + "'"
    s, o, e = ssh.exec_command(cmd, timeout=15)
    out = o.read().decode('utf-8', 'ignore').strip()
    print(js + ": " + out)

# Quick JS error check
ssh.exec_command('curl -s -c /tmp/cookies.txt "http://127.0.0.1:8080/vex/admin/admin" -d "admin_id=7146701713&password=Vex-LN36X_SG3bv-UNooqkME" > /dev/null', timeout=30)

errors = ['ReferenceError', 't is not defined', 'notifications is not defined', 'activityTicker is not defined', 'copied is not defined', 'tr is not defined', 'fmtNum is not defined', 'Alpine is not defined', 'baseApp is not defined']
for pattern in errors:
    cmd = 'curl -s -b /tmp/cookies.txt "http://127.0.0.1:8080/dashboard" | grep -c "' + pattern + '"'
    s, o, e = ssh.exec_command(cmd, timeout=15)
    out = o.read().decode('utf-8', 'ignore').strip()
    if out != '0':
        print(f"ERROR: {pattern} = {out}")

print("\nAll checks complete")

ssh.close()