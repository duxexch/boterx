import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

# Login first
ssh.exec_command('curl -s -c /tmp/admin_cookies.txt "http://127.0.0.1:8080/vex/admin/admin" -d "admin_id=7146701713&password=Vex-LN36X_SG3bv-UNooqkME"', timeout=30)

# Test fetch /api/stats with cookies
s, o, e = ssh.exec_command('curl -s -b /tmp/admin_cookies.txt -w "%{http_code}" "http://127.0.0.1:8080/api/stats"', timeout=15)
out = o.read().decode('utf-8', 'ignore').strip()

with open("debug_fetch.txt", "w", encoding="utf-8") as f:
    f.write(out)

ssh.close()
print('done')