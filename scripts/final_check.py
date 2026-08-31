import paramiko, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

import time

# Login first
stdin, stdout, stderr = ssh.exec_command("curl -sk -c /tmp/final_cookies.txt -X POST 'https://vex.deals/vex/admin/admin' -H 'Content-Type: application/x-www-form-urlencoded' -d 'admin_id=7146701713&password=Vex-LN36X_SG3bv-UNooqkME' -o /dev/null -w '%{http_code}'", timeout=15)
print("Login:", stdout.read().decode('utf-8', 'ignore').strip())
time.sleep(1)

print("\n=== FINAL PERFORMANCE CHECK ===")

# Test gzip on all major JS/CSS files
files_to_check = [
    '/static/js/app.js',
    '/static/js/i18n-admin-lexicon.js',
    '/static/js/admin-phrases.js',
    '/static/js/base-app.js',
    '/static/vendor/chart.umd.min.js',
    '/static/vendor/alpine.min.js',
    '/static/css/tailwind.build.css',
    '/static/css/style.css',
    '/static/vendor/fontawesome.min.css',
]

print("\n--- Gzip + Cache Headers ---")
for f in files_to_check:
    stdin, stdout, stderr = ssh.exec_command(f"curl -sI -H 'Accept-Encoding: gzip' 'https://vex.deals{f}' 2>/dev/null | grep -i 'content-encoding\\|cache-control\\|content-length' | tr '\\n' ' '", timeout=10)
    line = stdout.read().decode('utf-8', 'ignore').strip()
    print(f"{f.split('/')[-1]:40s} {line}")

# Test pages
print("\n--- Page Load Timing (with gzip + new code) ---")
for page in ['dashboard', 'users', 'transactions', 'games']:
    stdin, stdout, stderr = ssh.exec_command(f"curl -sk -b /tmp/final_cookies.txt 'https://vex.deals/{page}' -w 'TTFB: %{{time_starttransfer}}s Total: %{{time_total}}s Compressed: %{{size_download}}B' -o /dev/null 2>/dev/null", timeout=15)
    print(f"/{page}: {stdout.read().decode('utf-8', 'ignore').strip()}")

# Test users API
print("\n--- Users API ---")
stdin, stdout, stderr = ssh.exec_command("curl -sk -b /tmp/final_cookies.txt 'https://vex.deals/api/users?page=1&per_page=3' 2>/dev/null | python3 -c \"import sys,json; d=json.load(sys.stdin); print(f'Total: {d[\\\"total\\\"]}, Pages: {d[\\\"pages\\\"]}'); [print(f'  {u[\\\"date\\\"]} {u[\\\"name\\\"][:25]}') for u in d[\\\"users\\\"]]\"", timeout=15)
print(stdout.read().decode('utf-8', 'ignore').strip())

# Check version strings in rendered HTML
print("\n--- Version Strings in HTML ---")
stdin, stdout, stderr = ssh.exec_command("curl -sk -b /tmp/final_cookies.txt 'https://vex.deals/users' 2>/dev/null | grep -o 'app.js?v=[^\\\"]*\\|chart.umd[^\\\"]*\\|CACHE_VER\\|alpine.min.js'", timeout=15)
print(stdout.read().decode('utf-8', 'ignore').strip())

# Check SW version
print("\n--- Service Worker Version ---")
stdin, stdout, stderr = ssh.exec_command("grep 'CACHE_VER' /opt/bot/dashboard/static/sw.js", timeout=5)
print(stdout.read().decode('utf-8', 'ignore').strip())

# Check Google Fonts preconnect
print("\n--- Preconnect Hints ---")
stdin, stdout, stderr = ssh.exec_command("curl -sk -b /tmp/final_cookies.txt 'https://vex.deals/users' 2>/dev/null | grep -i 'preconnect'", timeout=10)
print(stdout.read().decode('utf-8', 'ignore').strip())

ssh.close()
