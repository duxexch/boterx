import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

print("=== 1. STOP SERVICES ===")
ssh.exec_command("systemctl stop boterx-dashboard.service boterx.service", timeout=30)
time.sleep(3)

print("=== 2. PULL LATEST CODE ===")
s, o, e = ssh.exec_command("cd /opt/bot && git fetch origin && git reset --hard origin/main", timeout=60)
out = o.read().decode('utf-8', 'ignore').strip()
err = e.read().decode('utf-8', 'ignore').strip()
print(out)
if err: print("ERR:", err)

print("=== 3. START SERVICES ===")
ssh.exec_command("systemctl start boterx-dashboard.service boterx.service", timeout=30)
time.sleep(5)

print("=== 4. VERIFY HEALTH ===")
s, o, e = ssh.exec_command("curl -s -o /dev/null -w 'health:%{http_code} time:%{time_total}\n' http://127.0.0.1:8080/health", timeout=10)
out = o.read().decode('utf-8', 'ignore').strip()
print(out)

print("=== 5. VERIFY SERVICES ===")
s, o, e = ssh.exec_command("systemctl is-active boterx-dashboard.service boterx.service", timeout=10)
out = o.read().decode('utf-8', 'ignore').strip()
print(out)

print("=== 6. LOGIN & CHECK DASHBOARD ===")
s, o, e = ssh.exec_command('curl -s -c /tmp/admin_cookies.txt -w "login:%{http_code}\n" "http://127.0.0.1:8080/vex/admin/admin" -d "admin_id=7146701713&password=Vex-LN36X_SG3bv-UNooqkME"', timeout=30)
out = o.read().decode('utf-8', 'ignore').strip()
print("Login:", out[-50:])

s, o, e = ssh.exec_command('curl -s -b /tmp/admin_cookies.txt -w "dashboard:%{http_code}\n" -o /dev/null "http://127.0.0.1:8080/dashboard"', timeout=30)
out = o.read().decode('utf-8', 'ignore').strip()
print(out)

print("=== 7. CHECK KEY PAGES ===")
for page in ["/dashboard", "/users", "/transactions", "/agents", "/broadcast", "/channels", "/ai-api-keys"]:
    s, o, e = ssh.exec_command(f'curl -s -b /tmp/admin_cookies.txt -w "%{{http_code}}" -o /dev/null "http://127.0.0.1:8080{page}"', timeout=15)
    out = o.read().decode('utf-8', 'ignore').strip()
    print(f"  {page}: {out}")

print("=== 8. CHECK SHOWCASE ===")
s, o, e = ssh.exec_command("curl -s -o /dev/null -w '%{http_code}' 'http://127.0.0.1:8080/x/showcase?k=eyJzY29wZSI6ImRlY2siLCJleHAiOjAsIm5vbmNlIjoibVFxSFp1aWdLTjVIIiwicGVybWFuZW50Ijp0cnVlfQ.9575f071aa4c3fb15a9c6c5fce498148e2a53749aa1ea6d3bb05f205cf7faf51'", timeout=15)
out = o.read().decode('utf-8', 'ignore').strip()
print(f"  Showcase: {out}")

print("=== 9. CHECK LOGS FOR ERRORS ===")
time.sleep(3)
s, o, e = ssh.exec_command("journalctl -u boterx-dashboard.service -n 30 --no-pager | grep -i 'error\\|exception\\|undefined\\|ReferenceError'", timeout=15)
out = o.read().decode('utf-8', 'ignore').strip()
if out:
    print("ERRORS FOUND:")
    print(out)
else:
    print("  No JS errors in logs")

print("\n=== DEPLOYMENT COMPLETE ===")
ssh.close()