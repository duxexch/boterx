import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

s, o, e = ssh.exec_command("wc -l /tmp/inline_1.js; echo '---'; tail -30 /tmp/inline_1.js", timeout=15)
out = o.read().decode('utf-8', 'ignore').strip()
with open('inline_tail.txt', 'w', encoding='utf-8') as f:
    f.write(out)
print(out)
ssh.close()