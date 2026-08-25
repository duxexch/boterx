import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=20)

# Try login with correct credentials
s, o, e = ssh.exec_command('curl -s -c /tmp/admin_cookies.txt -w "login:%{http_code} time:%{time_total}\n" "http://127.0.0.1:8080/vex/admin/admin" -d "admin_id=7146701713&password=Vex-LN36X_SG3bv-UNooqkME"', timeout=30)
out = o.read().decode('utf-8', 'ignore').strip()

with open('login_result3.txt', 'w', encoding='utf-8') as f:
    f.write(out)

# Now try to access dashboard
s, o, e = ssh.exec_command('curl -s -b /tmp/admin_cookies.txt -w "dashboard:%{http_code} time:%{time_total}\n" -o /dev/null "http://127.0.0.1:8080/dashboard"', timeout=30)
out = o.read().decode('utf-8', 'ignore').strip()

with open('dashboard_result2.txt', 'w', encoding='utf-8') as f:
    f.write(out)

# Also get the dashboard HTML
s, o, e = ssh.exec_command('curl -s -b /tmp/admin_cookies.txt "http://127.0.0.1:8080/dashboard"', timeout=30)
out = o.read().decode('utf-8', 'ignore').strip()

with open('dashboard_html2.txt', 'w', encoding='utf-8') as f:
    f.write(out[:10000])

print('Done - results in *_result.txt files')
ssh.close()