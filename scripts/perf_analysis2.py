import paramiko, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

# Find all nginx configs
stdin, stdout, stderr = ssh.exec_command("find /etc/nginx -name '*.conf' -o -name 'default' 2>/dev/null | xargs ls -la 2>/dev/null", timeout=10)
print("=== All nginx configs ===")
print(stdout.read().decode('utf-8', 'ignore'))

# Find the server block for vex.deals
stdin, stdout, stderr = ssh.exec_command("grep -rl 'vex\\|8080\\|dashboard' /etc/nginx/ 2>/dev/null", timeout=10)
files = stdout.read().decode('utf-8', 'ignore').strip()
print(f"\n=== Files mentioning vex/8080/dashboard: {files} ===")
for f in files.split('\n'):
    if f.strip():
        stdin, stdout, stderr = ssh.exec_command(f"cat {f.strip()}", timeout=10)
        content = stdout.read().decode('utf-8', 'ignore')
        print(f"\n--- {f} ---")
        print(content[:3000])

# Check sites-enabled
stdin, stdout, stderr = ssh.exec_command("ls -la /etc/nginx/sites-enabled/", timeout=10)
print("\n=== sites-enabled ===")
print(stdout.read().decode('utf-8', 'ignore'))

# Check conf.d
stdin, stdout, stderr = ssh.exec_command("ls -la /etc/nginx/conf.d/", timeout=10)
print("\n=== conf.d ===")
print(stdout.read().decode('utf-8', 'ignore'))

# Check what's actually listening on 443
stdin, stdout, stderr = ssht = ssh.exec_command("nginx -T 2>/dev/null | grep -A 50 'server_name.*vex'", timeout=10)
print("\n=== vex server block ===")
print(stdout.read().decode('utf-8', 'ignore'))

# Check actual response headers
stdin, stdout, stderr = ssh.exec_command("curl -Isk 'https://vex.deals/' 2>/dev/null", timeout=10)
print("\n=== Response headers ===")
print(stdout.read().decode('utf-8', 'ignore'))

# Check static file headers
stdin, stdout, stderr = ssh.exec_command("curl -Isk 'https://vex.deals/static/js/app.js' 2>/dev/null", timeout=10)
print("\n=== Static file headers ===")
print(stdout.read().decode('utf-8', 'ignore'))

# Check what the homepage actually loads
stdin, stdout, stderr = ssh.exec_command("curl -sk -b /tmp/https_cookies.txt 'https://vex.deals/' -o /dev/null -w 'TTFB: %{time_starttransfer}s Total: %{time_total}s Size: %{size_download}B Redirects: %{num_redirects}' 2>/dev/null", timeout=10)
print("\n=== Homepage timing ===")
print(stdout.read().decode('utf-8', 'ignore'))

# Check read_csv performance
stdin, stdout, stderr = ssh.exec_command("python3 -c \"\nimport time\ncsvs = ['users.csv', 'transactions.csv']\nfor c in csvs:\n    t0=time.time()\n    with open(f'/opt/bot/{c}','r',encoding='utf-8-sig') as f: lines=f.readlines()\n    print(f'{c}: {len(lines)} lines in {time.time()-t0:.3f}s')\n\" 2>/dev/null", timeout=10)
print("\n=== CSV read speed ===")
print(stdout.read().decode('utf-8', 'ignore'))

ssh.close()
