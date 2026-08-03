import paramiko, sys
sys.stdout.reconfigure(encoding='utf-8')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@')

# Test the snatch URL
stdin, stdout, stderr = ssh.exec_command('curl -s -o /dev/null -w "%{http_code}" https://69.169.108.197.sslip.io/webapp/snatch 2>&1')
print(f'Snatch URL status: {stdout.read().decode().strip()}')

# Test with params
stdin, stdout, stderr = ssh.exec_command('curl -s -o /dev/null -w "%{http_code}" "https://69.169.108.197.sslip.io/webapp/snatch?uid=123&lang=ar" 2>&1')
print(f'Snatch URL with params status: {stdout.read().decode().strip()}')

# Get snippet of the response
stdin, stdout, stderr = ssh.exec_command('curl -s "https://69.169.108.197.sslip.io/webapp/snatch?uid=123&lang=ar" 2>&1 | head -5')
print(f'Response start:\n{stdout.read().decode().strip()[:300]}')

# Check nginx config for /webapp/
stdin, stdout, stderr = ssh.exec_command('grep -A5 "webapp" /etc/nginx/sites-enabled/* 2>/dev/null; grep -A5 "webapp" /etc/nginx/nginx.conf 2>/dev/null')
print(f'\nNginx webapp config:\n{stdout.read().decode().strip()}')

# Check if dashboard is serving /webapp/snatch directly
stdin, stdout, stderr = ssh.exec_command('curl -s http://localhost:8080/webapp/snatch 2>&1 | head -3')
print(f'\nDirect dashboard:\n{stdout.read().decode().strip()[:200]}')

ssh.close()
