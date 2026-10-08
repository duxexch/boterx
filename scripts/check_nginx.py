import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=10)

# Test /admins returns 302 (login redirect) not 403
stdin, stdout, stderr = ssh.exec_command('curl -s -o /dev/null -w "%{http_code}" https://vex.deals/admins -H "Host: vex.deals" --insecure')
print(f'/admins status: {stdout.read().decode().strip()}')

# Verify CSS has light-mode rules
stdin, stdout, stderr = ssh.exec_command('grep -c "light-mode" /opt/bot/dashboard/static/css/style.css')
print(f'light-mode CSS rules: {stdout.read().decode().strip()}')

# Verify admin_management.html has theme-aware classes
stdin, stdout, stderr = ssh.exec_command('grep -c "text-bright\\|text-dim\\|btn-primary" /opt/bot/dashboard/templates/admin_management.html')
print(f'Theme-aware classes in admin_management.html: {stdout.read().decode().strip()}')

# Test the page renders (login first)
stdin, stdout, stderr = ssh.exec_command('curl -s -c /tmp/cookies.txt -b /tmp/cookies.txt -X POST https://vex.deals/login -d "password=Vex-LN36X_SG3bv-UNooqkME" -H "Host: vex.deals" --insecure -o /dev/null -w "%{http_code}"')
print(f'Login: {stdout.read().decode().strip()}')

stdin, stdout, stderr = ssh.exec_command('curl -s -b /tmp/cookies.txt https://vex.deals/admins -H "Host: vex.deals" --insecure -o /dev/null -w "%{http_code}"')
print(f'/admins after login: {stdout.read().decode().strip()}')

ssh.close()
