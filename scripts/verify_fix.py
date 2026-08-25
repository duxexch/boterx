import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

# Check base.html x-data
s, o, e = ssh.exec_command("grep 'x-data' /opt/bot/dashboard/templates/base.html | head -1", timeout=10)
out = o.read().decode('utf-8', 'ignore').strip()
print("x-data:", out)

# Check base-app.js Alpine.data registration
s, o, e = ssh.exec_command("curl -s 'http://127.0.0.1:8080/static/js/base-app.js?v=20260825b' | tail -10", timeout=15)
out = o.read().decode('utf-8', 'ignore').strip()
print("\nbase-app.js end:")
print(out)

# Login and check dashboard
ssh.exec_command('curl -s -c /tmp/cookies.txt "http://127.0.0.1:8080/vex/admin/admin" -d "admin_id=7146701713&password=Vex-LN36X_SG3bv-UNooqkME" > /dev/null', timeout=30)
s, o, e = ssh.exec_command('curl -s -b /tmp/cookies.txt "http://127.0.0.1:8080/dashboard"', timeout=30)
out = o.read().decode('utf-8', 'ignore').strip()

# Check for x-data in dashboard
import re
match = re.search(r'x-data="([^"]*)"', out)
if match:
    print(f"\nDashboard x-data: {match.group(1)}")

# Check sidebar text elements
sidebar_texts = re.findall(r'x-text="t\([^)]*\)"', out)
print(f"\nSidebar x-text elements: {len(sidebar_texts)}")
if sidebar_texts:
    print("First 5:", sidebar_texts[:5])

# Check toggles
if 'toggleLang' in out:
    print("toggleLang: FOUND")
if 'toggleDarkMode' in out:
    print("toggleDarkMode: FOUND")
if 'darkMode' in out:
    print("darkMode: FOUND")
if 'lang' in out:
    print("lang: FOUND")

ssh.close()