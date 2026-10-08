import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=20)

# Check static files
s, o, e = ssh.exec_command("curl -s -I 'http://127.0.0.1:8080/static/js/app.js?v=20260824b' | grep -i 'content-type\\|cache-control\\|last-modified'", timeout=30)
out = o.read().decode('utf-8', 'ignore').strip()

with open('static_check.txt', 'w', encoding='utf-8') as f:
    f.write(out + "\n\n")

s, o, e = ssh.exec_command("curl -s -I 'http://127.0.0.1:8080/static/js/base-app.js?v=20260824b' | grep -i 'content-type\\|cache-control\\|last-modified'", timeout=30)
out = o.read().decode('utf-8', 'ignore').strip()

with open('static_check.txt', 'a', encoding='utf-8') as f:
    f.write(out + "\n\n")

s, o, e = ssh.exec_command("curl -s -I 'http://127.0.0.1:8080/static/js/i18n-admin-runtime.js?v=20260824b' | grep -i 'content-type\\|cache-control\\|last-modified'", timeout=30)
out = o.read().decode('utf-8', 'ignore').strip()

with open('static_check.txt', 'a', encoding='utf-8') as f:
    f.write(out + "\n\n")

s, o, e = ssh.exec_command("curl -s -I 'http://127.0.0.1:8080/static/js/i18n-admin-lexicon.js?v=20260824b' | grep -i 'content-type\\|cache-control\\|last-modified'", timeout=30)
out = o.read().decode('utf-8', 'ignore').strip()

with open('static_check.txt', 'a', encoding='utf-8') as f:
    f.write(out)

print('Done')
ssh.close()