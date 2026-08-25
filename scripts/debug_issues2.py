import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

# Login first
ssh.exec_command('curl -s -c /tmp/admin_cookies.txt "http://127.0.0.1:8080/vex/admin/admin" -d "admin_id=7146701713&password=Vex-LN36X_SG3bv-UNooqkME"', timeout=30)

# Check dashboard HTML
s, o, e = ssh.exec_command('curl -s -b /tmp/admin_cookies.txt "http://127.0.0.1:8080/dashboard" > /tmp/dash_debug.html', timeout=30)

# Get toggles
s, o, e = ssh.exec_command("grep -n 'toggleLang\\|toggleDarkMode\\|baseApp\\|lang\\|darkMode' /tmp/dash_debug.html | head -30", timeout=15)
out = o.read().decode('utf-8', 'ignore').strip()

with open("debug_toggles.txt", "w", encoding="utf-8") as f:
    f.write(out)

print("=== TOGGLES ===")
print(out[:2000])

# Check script order
s, o, e = ssh.exec_command("grep -n 'static/js/' /opt/bot/dashboard/templates/base.html | head -20", timeout=15)
out = o.read().decode('utf-8', 'ignore').strip()

with open("debug_scripts.txt", "w", encoding="utf-8") as f:
    f.write(out)

print("\n=== SCRIPT ORDER ===")
print(out)

# Check base-app.js content
s, o, e = ssh.exec_command("curl -s 'http://127.0.0.1:8080/static/js/base-app.js?v=20260824b' | head -c 1000", timeout=15)
out = o.read().decode('utf-8', 'ignore').strip()

with open("debug_baseapp.txt", "w", encoding="utf-8") as f:
    f.write(out)

print("\n=== BASE-APP.JS ===")
print(out[:1000])

# Check logs
s, o, e = ssh.exec_command("journalctl -u boterx-dashboard.service -n 30 --no-pager", timeout=15)
out = o.read().decode('utf-8', 'ignore').strip()

with open("debug_logs.txt", "w", encoding="utf-8") as f:
    f.write(out)

print("\n=== LOGS ===")
print(out[-1500:])

ssh.close()