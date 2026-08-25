import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

def run(cmd, timeout=30):
    s, o, e = ssh.exec_command(cmd, timeout=timeout)
    return o.read().decode('utf-8', 'ignore').strip()

# Login + fetch live dashboard HTML
run('curl -s -c /tmp/ck.txt "http://127.0.0.1:8080/vex/admin/admin" -d "admin_id=7146701713&password=Vex-LN36X_SG3bv-UNooqkME" -o /dev/null')
run('curl -s -b /tmp/ck.txt "http://127.0.0.1:8080/dashboard" -o /tmp/dash_live.html')

# Upload checker via SFTP
sftp = ssh.open_sftp()
sftp.put('scripts/inline_checker.py', '/tmp/inline_checker.py')
sftp.close()

out = run('python3 /tmp/inline_checker.py', timeout=60)
with open('inline_check2.txt', 'w', encoding='utf-8') as f:
    f.write(out)

print(out[:3000])
ssh.close()