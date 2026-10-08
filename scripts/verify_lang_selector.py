import paramiko, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

stdin, stdout, stderr = ssh.exec_command('curl -sk "https://vex.deals/" 2>/dev/null | grep -c "langSelect"', timeout=10)
count = stdout.read().decode('utf-8','ignore').strip()
print(f"langSelect element found: {count}")

stdin, stdout, stderr = ssh.exec_command('curl -sk "https://vex.deals/" 2>/dev/null | grep -c "🇸🇦"', timeout=10)
count2 = stdout.read().decode('utf-8','ignore').strip()
print(f"Arabic flag in dropdown: {count2}")

stdin, stdout, stderr = ssh.exec_command('curl -sk "https://vex.deals/" 2>/dev/null | grep -c "🇺🇸"', timeout=10)
count3 = stdout.read().decode('utf-8','ignore').strip()
print(f"English flag in dropdown: {count3}")

stdin, stdout, stderr = ssh.exec_command('curl -sk "https://vex.deals/" 2>/dev/null | grep -c "changeLang"', timeout=10)
count4 = stdout.read().decode('utf-8','ignore').strip()
print(f"changeLang function in page: {count4}")

ssh.close()