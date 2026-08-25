import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

def run(cmd, timeout=20):
    s, o, e = ssh.exec_command(cmd, timeout=timeout)
    return o.read().decode('utf-8', 'ignore').strip()

# Login
run('curl -s -c /tmp/ck.txt "http://127.0.0.1:8080/vex/admin/admin" -d "admin_id=7146701713&password=Vex-LN36X_SG3bv-UNooqkME" -o /dev/null')

# Extract inline scripts and syntax-check each with node on the server
script = r'''
import re, subprocess, html as H
html_src = open('/tmp/dash_live.html', encoding='utf-8').read()
blocks = re.findall(r'<script(?![^>]*src=)[^>]*>(.*?)</script>', html_src, re.S)
print("inline scripts found:", len(blocks))
for i, b in enumerate(blocks):
    src = H.unescape(b)
    p = f'/tmp/inline_{i}.js'
    open(p, 'w', encoding='utf-8').write(src)
    r = subprocess.run(['node', '--check', p], capture_output=True, text=True)
    status = 'OK' if r.returncode == 0 else 'SYNTAX ERROR'
    print(f'--- script #{i}: {status}')
    if r.returncode != 0:
        print(r.stderr[:600])
        # show context around the failure
        lines = src.split('\n')
        print('first 3 lines:', '\n'.join(lines[:3])[:300])
'''
run('curl -s -b /tmp/ck.txt "http://127.0.0.1:8080/dashboard" -o /tmp/dash_live.html')
s, o, e = ssh.exec_command('python3 -c "' + script.replace('"', '\\"').replace('\n', '; ') + '"', timeout=60)
out = o.read().decode('utf-8', 'ignore').strip()
err = e.read().decode('utf-8', 'ignore').strip()
with open('inline_check.txt', 'w', encoding='utf-8') as f:
    f.write(out + ('\nSTDERR:\n' + err if err else ''))

# grep addEventEventListener typo in templates
typo = run("grep -rn 'addEventEventListener' /opt/bot/dashboard/templates/ /opt/bot/dashboard/static/js/ 2>/dev/null | head -5")
with open('inline_check.txt', 'a', encoding='utf-8') as f:
    f.write('\n\n=== addEventEventListener typo ===\n' + (typo or '(not found)'))

print("done")
ssh.close()