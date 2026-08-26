import paramiko, time, sys
sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

def run(cmd, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    return stdout.read().decode('utf-8', 'ignore').strip(), stderr.read().decode('utf-8', 'ignore').strip()

# 1. Check if JavaScript in channels.html has syntax errors
print('=== Python syntax check ===')
out, _ = run("python3 -c \"import py_compile; py_compile.compile('/opt/bot/dashboard/app.py', doraise=True); print('app.py OK')\" 2>&1")
print(out)

# 2. Check the rendered page for JS errors by looking at the HTML source
print('\n=== Channels page HTML length ===')
out, _ = run("curl -s -b /tmp/final.txt http://127.0.0.1:8080/channels 2>&1 | wc -c")
print(out)

# 3. Extract and check the channelsApp function
print('\n=== Check channels.js for errors ===')
out, _ = run("curl -s -b /tmp/final.txt http://127.0.0.1:8080/channels 2>&1 | grep -c 'channelsApp'")
print(out)

# 4. Check the static JS files
print('\n=== app.js exists ===')
out, _ = run("ls -la /opt/bot/dashboard/static/js/app.js")
print(out)

print('\n=== admin-phrases.js exists ===')
out, _ = run("ls -la /opt/bot/dashboard/static/js/admin-phrases.js")
print(out)

# 5. Check the actual page source around the Alpine init
print('\n=== Check Alpine.js loaded ===')
out, _ = run("curl -s http://127.0.0.1:8080/static/js/app.js 2>&1 | head -c 200")
print(out)

# 6. Check if the template renders properly on server
print('\n=== Login via form and get rendered page ===')
# Login first
out, _ = run("curl -s -c /tmp/session.txt 'http://127.0.0.1:8080/vex/admin/admin' -d 'admin_id=7146701713&password=Vex-LN36X_SG3bv-UNooqkME' -o /dev/null -w '%{http_code}' 2>&1")
print(f"Login HTTP: {out}")

# Get the page
out, _ = run("curl -s -b /tmp/session.txt 'http://127.0.0.1:8080/channels' 2>&1 | wc -c")
print(f"Page size: {out}")

# 7. Check for any JS errors in the page
print('\n=== Check for Alpine x-data ===')
out, _ = run("curl -s -b /tmp/session.txt 'http://127.0.0.1:8080/channels' 2>&1 | grep -o 'x-data=\"channelsApp()\"' | head -1")
print(out)

# 8. Check static files are served correctly
print('\n=== Static files check ===')
out, _ = run("curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/static/js/app.js")
print(f"app.js: {out}")

out, _ = run("curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/static/js/admin-phrases.js")
print(f"admin-phrases.js: {out}")

# 9. Check Alpine CDN
print('\n=== Alpine CDN ===')
out, _ = run("curl -s -b /tmp/session.txt 'http://127.0.0.1:8080/channels' 2>&1 | grep -i 'alpine' | head -3")
print(out)

# 10. Check the full JS block for parse errors
print('\n=== Extract JS block and check ===')
out, _ = run("curl -s -b /tmp/session.txt 'http://127.0.0.1:8080/channels' 2>&1 | sed -n '/<script>/,/<\\/script>/p' > /tmp/channels_js.txt 2>&1; wc -l /tmp/channels_js.txt")
print(out)

# Check with node if available
out, _ = run("which node 2>/dev/null && node --check /tmp/channels_js.txt 2>&1 || echo 'node not available'")
print(out)

ssh.close()
