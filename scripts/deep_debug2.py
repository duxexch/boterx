import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

# Save all output to files
def run_cmd(cmd, fname):
    s, o, e = ssh.exec_command(cmd, timeout=30)
    out = o.read().decode('utf-8', 'ignore').strip()
    with open(fname, "w", encoding="utf-8") as f:
        f.write(out)
    return out

run_cmd("journalctl -u boterx-dashboard.service -n 50 --no-pager", "debug_service_logs.txt")
run_cmd("tail -20 /var/log/nginx/access.log 2>/dev/null || echo 'No nginx logs'", "debug_nginx_access.txt")
run_cmd("tail -20 /var/log/nginx/error.log 2>/dev/null || echo 'No nginx error logs'", "debug_nginx_error.txt")
run_cmd("ls -la /opt/bot/dashboard/static/js/*.js", "debug_js_files.txt")
run_cmd("grep -n 'script src' /opt/bot/dashboard/templates/base.html", "debug_base_html.txt")

# Login and get dashboard
ssh.exec_command('curl -s -c /tmp/cookies.txt "http://127.0.0.1:8080/vex/admin/admin" -d "admin_id=7146701713&password=Vex-LN36X_SG3bv-UNooqkME" > /dev/null', timeout=30)
run_cmd('curl -s -b /tmp/cookies.txt "http://127.0.0.1:8080/dashboard"', "debug_dashboard.html")

# Check for specific JS errors
errors = ['ReferenceError', 't is not defined', 'notifications is not defined', 'activityTicker is not defined', 'copied is not defined', 'tr is not defined', 'fmtNum is not defined', 'Alpine is not defined']
with open("debug_js_errors.txt", "w", encoding="utf-8") as f:
    for pattern in errors:
        s, o, e = ssh.exec_command(f'curl -s -b /tmp/cookies.txt "http://127.0.0.1:8080/dashboard" | grep -c "{pattern}"', timeout=15)
        out = o.read().decode('utf-8', 'ignore').strip()
        if out != '0':
            f.write(f"FOUND: {pattern} = {out}\n")
        else:
            f.write(f"OK: {pattern} = 0\n")

# Check static files served
for js in ['app.js', 'base-app.js', 'i18n-admin-runtime.js', 'i18n-admin-lexicon.js', 'alpine.min.js']:
    s, o, e = ssh.exec_command(f"curl -s -I 'http://127.0.0.1:8080/static/js/{js}?v=20260825a' | head -5", timeout=15)
    out = o.read().decode('utf-8', 'ignore').strip()
    with open(f"debug_static_{js}.txt", "w", encoding="utf-8") as f:
        f.write(out)

ssh.close()
print("Done - check debug_*.txt files")