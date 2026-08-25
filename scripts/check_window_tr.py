import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

# Check full i18n-admin-runtime.js
s, o, e = ssh.exec_command("curl -s 'http://127.0.0.1:8080/static/js/i18n-admin-runtime.js?v=20260825a'", timeout=15)
out = o.read().decode('utf-8', 'ignore').strip()
with open("full_i18n_runtime.txt", "w", encoding="utf-8") as f:
    f.write(out)
print("Saved full_i18n_runtime.txt")
print("Length:", len(out))

# Check if window.tr is in it
if "window.tr" in out:
    print("window.tr FOUND")
else:
    print("window.tr NOT FOUND - THIS IS THE BUG!")

ssh.close()