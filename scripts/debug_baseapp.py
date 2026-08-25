import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

s, o, e = ssh.exec_command("curl -s 'http://127.0.0.1:8080/static/js/base-app.js?v=20260824b'", timeout=15)
out = o.read().decode('utf-8', 'ignore').strip()

with open("debug_baseapp2.txt", "w", encoding="utf-8") as f:
    f.write(out)

ssh.close()
print('done')