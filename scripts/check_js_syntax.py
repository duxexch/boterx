import paramiko, sys
sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

def run(cmd, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    return stdout.read().decode('utf-8', 'ignore').strip(), stderr.read().decode('utf-8', 'ignore').strip()

# Check app.js for JS syntax errors
print('=== app.js JS syntax check ===')
out, _ = run("node --check /opt/bot/dashboard/static/js/app.js 2>&1")
print(out or "OK")

print('\n=== admin-phrases.js JS syntax check ===')
out, _ = run("node --check /opt/bot/dashboard/static/js/admin-phrases.js 2>&1")
print(out or "OK")

# Check i18n-admin-runtime.js
print('\n=== i18n-admin-runtime.js ===')
out, _ = run("ls -la /opt/bot/dashboard/static/js/i18n-admin-runtime.js 2>&1")
print(out)

print('\n=== i18n-admin-lexicon.js ===')
out, _ = run("ls -la /opt/bot/dashboard/static/js/i18n-admin-lexicon.js 2>&1")
print(out)

# Extract the inline JS from rendered channels page and save as .js file
print('\n=== Extract inline JS ===')
run("curl -s -b /tmp/session.txt 'http://127.0.0.1:8080/channels' 2>&1 | sed -n '/<script>$/,/<\\/script>/p' | sed '1d;$d' > /tmp/channels_inline.js")
out, _ = run("wc -l /tmp/channels_inline.js")
print(out)

print('\n=== Inline JS syntax check ===')
out, _ = run("node --check /tmp/channels_inline.js 2>&1")
print(out or "OK")

# Copy to local for analysis
ssh.close()
print("DONE")
