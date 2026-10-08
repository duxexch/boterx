import paramiko, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

# Test language change via URL parameter
stdin, stdout, stderr = ssh.exec_command('curl -sk "https://vex.deals/?lang=en" 2>/dev/null | grep -c "Browse Companies"', timeout=10)
print("English page loads:", stdout.read().decode('utf-8','ignore').strip())

stdin, stdout, stderr = ssh.exec_command('curl -sk "https://vex.deals/?lang=fr" 2>/dev/null | grep -c "Parcourir"', timeout=10)
print("French page loads:", stdout.read().decode('utf-8','ignore').strip())

stdin, stdout, stderr = ssh.exec_command('curl -sk "https://vex.deals/?lang=es" 2>/dev/null | grep -c "Explorar"', timeout=10)
print("Spanish page loads:", stdout.read().decode('utf-8','ignore').strip())

stdin, stdout, stderr = ssh.exec_command('curl -sk "https://vex.deals/?lang=zh" 2>/dev/null | grep -c "全球"', timeout=10)
print("Chinese page loads:", stdout.read().decode('utf-8','ignore').strip())

ssh.close()