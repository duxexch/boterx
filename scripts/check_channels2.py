import paramiko, time, sys
sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

def run(cmd, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    return stdout.read().decode('utf-8', 'ignore').strip(), stderr.read().decode('utf-8', 'ignore').strip()

# Check if read_csv works in app.py context
print('=== CSV file bytes (first 20) ===')
out, _ = run("head -c 100 /opt/bot/bot_channels.csv | xxd | head -5")
print(out)

print('\n=== CSV line count (wc -l) ===')
out, _ = run("wc -l /opt/bot/bot_channels.csv")
print(out)

print('\n=== CSV python read test ===')
out, _ = run('python3 -c "import csv; f=open(\'/opt/bot/bot_channels.csv\',\'r\',encoding=\'utf-8-sig\'); r=list(csv.DictReader(f)); f.close(); print(len(r),\'rows\')"')
print(out)

print('\n=== getcwd / working dir ===')
out, _ = run('ls -la /opt/bot/bot_channels.csv')
print(out)

print('\n=== Check if app.py reads from correct BASE_DIR ===')
out, _ = run('python3 -c "import os; print(os.path.dirname(os.path.dirname(os.path.abspath(\'/opt/bot/dashboard/app.py\'))))"')
print(out)

# The key issue: check _admin_can_manage_channel
print('\n=== API with session cookie test ===')
out, _ = run('curl -s http://127.0.0.1:8080/api/channels -H "X-API-Key: vex_hermes_FkVWYOPLZ230Ru22ib0vRDDKOJL4agfhSBDUuUoMQIM" | head -c 200')
print(out)

# Check _normalize_channel_row
print('\n=== Test admin auth + session ===')
out, _ = run('curl -s -c /tmp/cookies.txt -b /tmp/cookies.txt http://127.0.0.1:8080/api/channels -H "X-API-Key: vex_hermes_FkVWYOPLZ230Ru22ib0vRDDKOJL4agfhSBDUuUoMQIM" | head -c 300')
print(out)

# Check for any Python errors in dashboard startup
print('\n=== Dashboard startup full log ===')
out, _ = run('journalctl -u boterx-dashboard.service --no-pager -n 50 2>&1 | grep -i "error\\|warn\\|channel\\|csv"')
print(out)

ssh.close()
