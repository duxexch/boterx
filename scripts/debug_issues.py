import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

# Check static files are accessible and correct
print("=== 1. CHECK STATIC JS FILES ===")
for js_file in ["app.js", "base-app.js", "i18n-admin-runtime.js", "i18n-admin-lexicon.js"]:
    s, o, e = ssh.exec_command(f"curl -s -I 'http://127.0.0.1:8080/static/js/{js_file}?v=20260824b' | grep -i 'content-type\\|content-length\\|cache-control'", timeout=15)
    out = o.read().decode('utf-8', 'ignore').strip()
    print(f"  {js_file}:")
    for line in out.split('\n'):
        print(f"    {line}")

print("\n=== 2. CHECK LOGIN PAGE SPEED ===")
s, o, e = ssh.exec_command("curl -s -o /dev/null -w 'login:%{http_code} time:%{time_total} size:%{size_download}\n' 'http://127.0.0.1:8080/vex/admin/admin'", timeout=30)
out = o.read().decode('utf-8', 'ignore').strip()
print(out)

print("\n=== 3. CHECK DASHBOARD HTML FOR TOGGLES ===")
s, o, e = ssh.exec_command('curl -s -b /tmp/admin_cookies.txt "http://127.0.0.1:8080/dashboard" | grep -n "toggleLang\\|toggleDarkMode\\|baseApp\\|lang\\|darkMode" | head -20', timeout=30)
out = o.read().decode('utf-8', 'ignore').strip()
print(out)

print("\n=== 4. CHECK SCRIPT LOADING ORDER IN BASE.HTML ===")
s, o, e = ssh.exec_command("grep -n 'static/js/' /opt/bot/dashboard/templates/base.html | head -20", timeout=15)
out = o.read().decode('utf-8', 'ignore').strip()
print(out)

print("\n=== 5. CHECK IF ALPINE LOADS BEFORE BASE-APP ===")
s, o, e = ssh.exec_command("curl -s 'http://127.0.0.1:8080/static/js/base-app.js?v=20260824b' | head -c 500", timeout=15)
out = o.read().decode('utf-8', 'ignore').strip()
print(out[:500])

print("\n=== 6. RECENT LOGS ===")
s, o, e = ssh.exec_command("journalctl -u boterx-dashboard.service -n 20 --no-pager", timeout=15)
out = o.read().decode('utf-8', 'ignore').strip()
print(out[-1000:])

ssh.close()