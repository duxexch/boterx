import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

# Check base.html script tags
s, o, e = ssh.exec_command("cat /opt/bot/dashboard/templates/base.html | grep -n 'script src'", timeout=15)
out = o.read().decode('utf-8', 'ignore').strip()

with open("debug_scripts2.txt", "w", encoding="utf-8") as f:
    f.write(out)

ssh.close()
print('done')