import paramiko, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

# Check for lang-selector class and custom dropdown
stdin, stdout, stderr = ssh.exec_command('curl -sk "https://vex.deals/" 2>/dev/null | grep -c "lang-selector"', timeout=10)
print("lang-selector class:", stdout.read().decode('utf-8','ignore').strip())

stdin, stdout, stderr = ssh.exec_command('curl -sk "https://vex.deals/" 2>/dev/null | grep -c "lang-trigger"', timeout=10)
print("lang-trigger class:", stdout.read().decode('utf-8','ignore').strip())

stdin, stdout, stderr = ssh.exec_command('curl -sk "https://vex.deals/" 2>/dev/null | grep -c "lang-menu"', timeout=10)
print("lang-menu class:", stdout.read().decode('utf-8','ignore').strip())

stdin, stdout, stderr = ssh.exec_command('curl -sk "https://vex.deals/" 2>/dev/null | grep -c "lang-search"', timeout=10)
print("lang-search input:", stdout.read().decode('utf-8','ignore').strip())

stdin, stdout, stderr = ssh.exec_command('curl -sk "https://vex.deals/" 2>/dev/null | grep -c "lang-list"', timeout=10)
print("lang-list:", stdout.read().decode('utf-8','ignore').strip())

stdin, stdout, stderr = ssh.exec_command('curl -sk "https://vex.deals/" 2>/dev/null | grep -c "toggleLangMenu"', timeout=10)
print("toggleLangMenu function:", stdout.read().decode('utf-8','ignore').strip())

stdin, stdout, stderr = ssh.exec_command('curl -sk "https://vex.deals/" 2>/dev/null | grep -c "closeLangMenu"', timeout=10)
print("closeLangMenu function:", stdout.read().decode('utf-8','ignore').strip())

stdin, stdout, stderr = ssh.exec_command('curl -sk "https://vex.deals/" 2>/dev/null | grep -c "filterLang"', timeout=10)
print("filterLang function:", stdout.read().decode('utf-8','ignore').strip())

# Check if language change works
stdin, stdout, stderr = ssh.exec_command('curl -sk "https://vex.deals/?lang=en" 2>/dev/null | grep -c "Browse Companies"', timeout=10)
print("English works:", stdout.read().decode('utf-8','ignore').strip())

stdin, stdout, stderr = ssh.exec_command('curl -sk "https://vex.deals/?lang=fr" 2>/dev/null | grep -c "Parcourir"', timeout=10)
print("French works:", stdout.read().decode('utf-8','ignore').strip())

ssh.close()