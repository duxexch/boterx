import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=20)

# Health and services
s, o, e = ssh.exec_command("curl -s -o /dev/null -w 'health:%{http_code} time:%{time_total}\n' http://127.0.0.1:8080/health", timeout=10)
out = o.read().decode('utf-8', 'ignore').strip()
print(out)

s, o, e = ssh.exec_command("systemctl is-active boterx-dashboard.service boterx.service", timeout=10)
out = o.read().decode('utf-8', 'ignore').strip()
print(out)

# Check if port 8080 is listening
s, o, e = ssh.exec_command("ss -tlnp | grep :8080", timeout=10)
out = o.read().decode('utf-8', 'ignore').strip()
print(out)

print("Done")
ssh.close()