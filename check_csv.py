import paramiko, sys
sys.stdout.reconfigure(encoding='utf-8')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@')

# Check if wheel_gifts.csv has any active gifts
stdin, stdout, stderr = ssh.exec_command('cat /opt/bot/wheel_gifts.csv 2>/dev/null')
print('=== wheel_gifts.csv ===')
print(stdout.read().decode('utf-8'))

# Check if wheel_rounds.csv has any active rounds
stdin, stdout, stderr = ssh.exec_command('cat /opt/bot/wheel_rounds.csv 2>/dev/null')
print('\n=== wheel_rounds.csv ===')
print(stdout.read().decode('utf-8'))

ssh.close()
