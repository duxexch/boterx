import paramiko, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

# Fix nginx: use only Cache-Control (remove expires directive for static), and use longer cache
cmd = """python3 -c "
with open('/etc/nginx/sites-available/vex.deals', 'r') as f:
    content = f.read()

# Replace the static location block with optimized version
old = '''    location /static/ {
        alias /opt/bot/dashboard/static/;
        expires 30d;
        add_header Cache-Control \\"public, max-age=86400\\";
    }'''

new = '''    location /static/ {
        alias /opt/bot/dashboard/static/;
        add_header Cache-Control \\"public, max-age=2592000, immutable\\";
        gzip_static on;
    }'''

content = content.replace(old, new)

# Also fix the sw.js cache-control to no-store + no-cache
old2 = '''    location = /static/sw.js {
        alias /opt/bot/dashboard/static/sw.js;
        add_header Cache-Control \\"no-cache, no-store, must-revalidate\\";
        expires off;
    }'''

new2 = '''    location = /static/sw.js {
        alias /opt/bot/dashboard/static/sw.js;
        add_header Cache-Control \\"no-cache, no-store, must-revalidate\\";
        add_header Pragma \\"no-cache\\";
        expires off;
    }'''

content = content.replace(old2, new2)

with open('/etc/nginx/sites-available/vex.deals', 'w') as f:
    f.write(content)
print('Fixed vex.deals nginx config')

# Do the same for the symlinked file
import shutil, os
try:
    shutil.copy2('/etc/nginx/sites-available/vex.deals', '/etc/nginx/sites-enabled/vex.deals')
    print('Copied to sites-enabled')
except:
    print('Copy failed, checking symlink...')
    if os.path.islink('/etc/nginx/sites-enabled/vex.deals'):
        target = os.readlink('/etc/nginx/sites-enabled/vex.deals')
        print(f'Symlink points to: {target}')
" """
stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
print(stdout.read().decode('utf-8', 'ignore').strip())

# Test and reload
stdin, stdout, stderr = ssh.exec_command("nginx -t 2>&1", timeout=10)
print("Nginx test:", stdout.read().decode('utf-8', 'ignore').strip())

stdin, stdout, stderr = ssh.exec_command("nginx -s reload 2>&1", timeout=10)
print("Nginx reload:", stdout.read().decode('utf-8', 'ignore').strip())

# Verify
import time; time.sleep(1)
stdin, stdout, stderr = ssh.exec_command("curl -sI -H 'Accept-Encoding: gzip' 'https://vex.deals/static/js/app.js' 2>/dev/null | head -15", timeout=10)
print("Headers after fix:", stdout.read().decode('utf-8', 'ignore').strip())

ssh.close()
