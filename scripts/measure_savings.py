import paramiko, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

files = [
    '/static/js/app.js',
    '/static/js/i18n-admin-lexicon.js',
    '/static/js/admin-phrases.js',
    '/static/js/base-app.js',
    '/static/js/game-base.js',
    '/static/vendor/alpine.min.js',
    '/static/vendor/chart.umd.min.js',
    '/static/css/tailwind.build.css',
    '/static/css/style.css',
    '/static/css/user-themes.css',
    '/static/vendor/fontawesome.min.css',
]

total_raw = 0
total_gzip = 0

for f in files:
    # Get raw size
    stdin, stdout, stderr = ssh.exec_command(f"stat -c %s /opt/bot/dashboard/static/{f.split('/static/')[-1]}", timeout=5)
    raw = int(stdout.read().decode("utf-8", "ignore").strip() or 0)
    
    # Get gzip size
    stdin, stdout, stderr = ssh.exec_command(f"curl -sk -H 'Accept-Encoding: gzip' 'https://vex.deals{f}' -w '%{{size_download}}' -o /tmp/gz_test 2>/dev/null", timeout=10)
    gzip_size = int(stdout.read().decode("utf-8", "ignore").strip() or 0)
    
    savings = ((raw - gzip_size) / raw * 100) if raw > 0 else 0
    total_raw += raw
    total_gzip += gzip_size
    print(f"{f.split('/')[-1]:40s} {raw:>8,} B -> {gzip_size:>8,} B  ({savings:.0f}% saved)")

print(f"\n{'TOTAL':40s} {total_raw:>8,} B -> {total_gzip:>8,} B  ({(total_raw-total_gzip)/total_raw*100:.0f}% saved)")
print(f"Savings: {(total_raw-total_gzip):,} bytes = {(total_raw-total_gzip)/1024:.1f} KB")

# Now test full page load timing
print("\n=== Page Load Timing (before vs after) ===")
for page in ['dashboard', 'users', 'games']:
    stdin, stdout, stderr = ssh.exec_command(f"curl -sk -b /tmp/https_cookies.txt 'https://vex.deals/{page}' -w 'TTFB: %{{time_starttransfer}}s Total: %{{time_total}}s Size: %{{size_download}}B' -o /dev/null 2>/dev/null", timeout=15)
    print(f"/{page}: {stdout.read().decode('utf-8', 'ignore').strip()}")

# Test static file delivery
print("\n=== Static File Delivery ===")
stdin, stdout, stderr = ssh.exec_command("curl -sk -H 'Accept-Encoding: gzip' 'https://vex.deals/static/js/app.js' -w 'TTFB: %{time_starttransfer}s Total: %{time_total}s Size: %{size_download}B' -o /dev/null 2>/dev/null", timeout=10)
print(f"app.js: {stdout.read().decode('utf-8', 'ignore').strip()}")

ssh.close()
