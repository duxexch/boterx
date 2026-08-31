import paramiko, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

# 1. Check nginx config
print("=== 1. NGINX CONFIG ===")
stdin, stdout, stderr = ssh.exec_command("cat /etc/nginx/sites-enabled/default 2>/dev/null || cat /etc/nginx/nginx.conf 2>/dev/null | head -100", timeout=10)
print(stdout.read().decode('utf-8', 'ignore')[:3000])

# Find vex.deals nginx config
stdin, stdout, stderr = ssh.exec_command("find /etc/nginx -name '*.conf' -exec grep -l 'vex' {} \\; 2>/dev/null", timeout=10)
conf_files = stdout.read().decode('utf-8', 'ignore').strip()
print(f"\nNginx conf files with 'vex': {conf_files}")

for f in conf_files.split('\n'):
    if f.strip():
        stdin, stdout, stderr = ssh.exec_command(f"cat {f.strip()}", timeout=10)
        print(f"\n=== {f} ===")
        print(stdout.read().decode('utf-8', 'ignore')[:3000])

# 2. Check all static file sizes
print("\n\n=== 2. STATIC FILE SIZES ===")
stdin, stdout, stderr = ssh.exec_command("ls -lhS /opt/bot/dashboard/static/js/*.js /opt/bot/dashboard/static/css/*.css 2>/dev/null", timeout=10)
print(stdout.read().decode('utf-8', 'ignore'))

# 3. Check template sizes
print("\n=== 3. TEMPLATE SIZES ===")
stdin, stdout, stderr = ssh.exec_command("ls -lhS /opt/bot/dashboard/templates/*.html 2>/dev/null | head -20", timeout=10)
print(stdout.read().decode('utf-8', 'ignore'))

# 4. Check base.html total size rendered
print("\n=== 4. RENDERED PAGE SIZES ===")
# Login and check each major page size
for page in ['dashboard', 'users', 'transactions', 'games', 'rental']:
    stdin, stdout, stderr = ssh.exec_command(f"curl -sk -b /tmp/https_cookies.txt 'https://vex.deals/{page}' -w '\\nSIZE: %{{size_download}} TIME: %{{time_total}}' -o /dev/null 2>/dev/null", timeout=15)
    print(f"/{page}: {stdout.read().decode('utf-8', 'ignore').strip()}")

# 5. Check if gzip/brotli is enabled in nginx
print("\n=== 5. NGINX COMPRESSION ===")
stdin, stdout, stderr = ssh.exec_command("nginx -T 2>/dev/null | grep -i 'gzip\\|brotli\\|compress' | head -20", timeout=10)
print(stdout.read().decode('utf-8', 'ignore'))

# 6. Check gunicorn workers/config
print("\n=== 6. GUNICORN CONFIG ===")
stdin, stdout, stderr = ssh.exec_command("ps aux | grep gunicorn | head -5", timeout=10)
print(stdout.read().decode('utf-8', 'ignore'))

stdin, stdout, stderr = ssh.exec_command("cat /etc/systemd/system/boterx-dashboard.service 2>/dev/null", timeout=10)
print(stdout.read().decode('utf-8', 'ignore'))

# 7. Check external resource load times
print("\n=== 7. EXTERNAL RESOURCES ===")
stdin, stdout, stderr = ssh.exec_command("curl -sw '\\nGoogle Fonts: %{time_total}s %{size_download}B\\n' -o /dev/null 'https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap' 2>/dev/null", timeout=10)
print(stdout.read().decode('utf-8', 'ignore'))

stdin, stdout, stderr = ssh.exec_command("curl -sw '\\nFontAwesome: %{time_total}s %{size_download}B\\n' -o /dev/null 'https://vex.deals/static/vendor/fontawesome.min.css' 2>/dev/null", timeout=10)
print(stdout.read().decode('utf-8', 'ignore'))

# 8. Check chart.js (is it even needed on every page?)
print("\n=== 8. chart.js SIZE ===")
stdin, stdout, stderr = ssh.exec_command("ls -lh /opt/bot/dashboard/static/vendor/chart.umd.min.js 2>/dev/null", timeout=10)
print(stdout.read().decode('utf-8', 'ignore'))

# 9. Check all vendor files
print("\n=== 9. VENDOR FILES ===")
stdin, stdout, stderr = ssh.exec_command("ls -lhS /opt/bot/dashboard/static/vendor/ 2>/dev/null", timeout=10)
print(stdout.read().decode('utf-8', 'ignore'))

# 10. Check if there are huge JS bundles
print("\n=== 10. ALL JS FILES SIZE ===")
stdin, stdout, stderr = ssh.exec_command("find /opt/bot/dashboard/static -name '*.js' -exec ls -lhS {} + 2>/dev/null | head -20", timeout=10)
print(stdout.read().decode('utf-8', 'ignore'))

# 11. Check all CSS files
print("\n=== 11. ALL CSS FILES SIZE ===")
stdin, stdout, stderr = ssh.exec_command("find /opt/bot/dashboard/static -name '*.css' -exec ls -lhS {} + 2>/dev/null | head -20", timeout=10)
print(stdout.read().decode('utf-8', 'ignore'))

# 12. Time actual page load with curl
print("\n=== 12. FULL PAGE LOAD TIMING ===")
stdin, stdout, stderr = ssh.exec_command("curl -sk -b /tmp/https_cookies.txt 'https://vex.deals/dashboard' -w 'DNS: %{time_namelookup}s\\nConnect: %{time_connect}s\\nTTFB: %{time_starttransfer}s\\nTotal: %{time_total}s\\nSize: %{size_download}B\\n' -o /dev/null 2>/dev/null", timeout=15)
print(stdout.read().decode('utf-8', 'ignore'))

ssh.close()
