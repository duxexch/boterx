import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=20)

# Check for language toggle and dark mode toggle in the dashboard
s, o, e = ssh.exec_command('curl -s -b /tmp/admin_cookies.txt "http://127.0.0.1:8080/dashboard" | grep -n "toggleLang\\|toggleDarkMode\\|lang\\|darkMode"', timeout=30)
out = o.read().decode('utf-8', 'ignore').strip()

with open('toggle_check.txt', 'w', encoding='utf-8') as f:
    f.write(out)

print('Done')
ssh.close()