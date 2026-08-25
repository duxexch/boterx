import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

# Check vendor directory
s, o, e = ssh.exec_command("ls -la /opt/bot/dashboard/static/vendor/", timeout=10)
out = o.read().decode('utf-8', 'ignore').strip()
with open("debug_vendor.txt", "w", encoding="utf-8") as f:
    f.write(out)
print(out)

# Check if alpine is in js folder
s, o, e = ssh.exec_command("find /opt/bot/dashboard/static -name 'alpine*'", timeout=10)
out = o.read().decode('utf-8', 'ignore').strip()
with open("debug_find_alpine.txt", "w", encoding="utf-8") as f:
    f.write(out)
print("\nFind alpine:", out)

ssh.close()