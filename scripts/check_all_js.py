import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

# Test all JS files loaded in dashboard
js_files = [
    "/static/vendor/chart.umd.min.js?v=20260825a",
    "/static/vendor/alpine.min.js?v=20260825a",
    "/static/js/app.js?v=20260825a",
    "/static/js/i18n-admin-lexicon.js?v=20260825a",
    "/static/js/i18n-admin-runtime.js?v=20260825a",
    "/static/js/base-app.js?v=20260825a",
]

for js in js_files:
    cmd = "curl -s -o /dev/null -w 'http_code:%{http_code} size:%{size_download}' 'http://127.0.0.1:8080" + js + "'"
    s, o, e = ssh.exec_command(cmd, timeout=15)
    out = o.read().decode('utf-8', 'ignore').strip()
    print(js + ": " + out)

# Check content of base-app.js to verify fixes
s, o, e = ssh.exec_command("curl -s 'http://127.0.0.1:8080/static/js/base-app.js?v=20260825a' | head -30", timeout=15)
out = o.read().decode('utf-8', 'ignore').strip()
print("\n=== base-app.js (first 30 lines) ===")
print(out)

# Check i18n-admin-runtime.js for window.tr
s, o, e = ssh.exec_command("curl -s 'http://127.0.0.1:8080/static/js/i18n-admin-runtime.js?v=20260825a' | tail -10", timeout=15)
out = o.read().decode('utf-8', 'ignore').strip()
print("\n=== i18n-admin-runtime.js (last 10 lines) ===")
print(out)

ssh.close()