import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=20)

s, o, e = ssh.exec_command('curl -s -c /tmp/admin_cookies.txt -w "login:%{http_code} time:%{time_total}\n" "http://127.0.0.1:8080/vex/admin/admin" -d "admin_id=1&password=M12122099m@@@@"', timeout=30)
out = o.read().decode('utf-8', 'ignore').strip()

with open("login_result.txt", "w", encoding="utf-8") as f:
    f.write(out)

print("Done - result in login_result.txt")

ssh.close()