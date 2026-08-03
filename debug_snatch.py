import paramiko, sys
sys.stdout.reconfigure(encoding='utf-8')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@')

# Check recent bot logs for snatch data
stdin, stdout, stderr = ssh.exec_command('journalctl -u boterx --no-pager -n 30 2>&1 | grep -i "snatch\|اختطف\|web_app_data\|gift"')
print('=== Snatch-related logs ===')
print(stdout.read().decode('utf-8')[:2000])

# Check wheel_spins.csv for recent entries
stdin, stdout, stderr = ssh.exec_command('tail -10 /opt/bot/wheel_spins.csv 2>/dev/null')
print('\n=== wheel_spins.csv (last 10) ===')
print(stdout.read().decode('utf-8'))

# Check svrp_wallets.csv
stdin, stdout, stderr = ssh.exec_command('cat /opt/bot/svrp_wallets.csv 2>/dev/null')
print('\n=== svrp_wallets.csv ===')
print(stdout.read().decode('utf-8')[:1000])

ssh.close()
