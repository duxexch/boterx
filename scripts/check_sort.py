import paramiko, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

# Check actual sort code on server
stdin, stdout, stderr = ssh.exec_command("sed -n '7490,7545p' /opt/bot/dashboard/app.py", timeout=10)
print("=== Server /api/users code ===")
print(stdout.read().decode('utf-8', 'ignore'))

# Check actual CSV data order
stdin, stdout, stderr = ssh.exec_command("head -3 /opt/bot/users.csv && echo '---' && tail -3 /opt/bot/users.csv", timeout=10)
print("\n=== CSV head/tail ===")
print(stdout.read().decode('utf-8', 'ignore'))

# Check how many users total
stdin, stdout, stderr = ssh.exec_command("wc -l /opt/bot/users.csv", timeout=10)
print("\n=== CSV line count ===")
print(stdout.read().decode('utf-8', 'ignore'))

# Test API page 1 and page 6 directly
stdin, stdout, stderr = ssh.exec_command("curl -sk -b /tmp/https_cookies.txt 'https://vex.deals/api/users?page=1&per_page=3' 2>/dev/null | python3 -c \"import sys,json; d=json.load(sys.stdin); [print(u['date'],u['name'][:20]) for u in d['users']]\"", timeout=15)
print("\n=== API page 1 (3 per page) ===")
print(stdout.read().decode('utf-8', 'ignore'))

stdin, stdout, stderr = ssh.exec_command("curl -sk -b /tmp/https_cookies.txt 'https://vex.deals/api/users?page=2&per_page=3' 2>/dev/null | python3 -c \"import sys,json; d=json.load(sys.stdin); [print(u['date'],u['name'][:20]) for u in d['users']]\"", timeout=15)
print("\n=== API page 2 (3 per page) ===")
print(stdout.read().decode('utf-8', 'ignore'))

ssh.close()
