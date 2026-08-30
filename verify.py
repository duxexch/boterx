import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=10)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=30)
    return stdout.read().decode('utf-8', errors='replace').strip()

run("""curl -s -c /tmp/r.txt -L -o /dev/null -X POST 'http://localhost:8080/vex/admin/admin' --data-urlencode 'admin_id=7146701713' --data-urlencode 'password=Vex-LN36X_SG3bv-UNooqkME'""")

for path in ['/rental', '/clients', '/bots', '/client-login', '/api/rental/pending-count', '/api/rental/payment-methods', '/api/rental/all-transactions']:
    code = run(f"curl -s -b /tmp/r.txt -o /dev/null -w '%{{http_code}}' 'http://localhost:8080{path}'")
    print(f'{path}: {code}')

# Check errors
err = run("journalctl -u boterx-dashboard --no-pager -n 5 2>&1 | grep -i 'error\\|exception' | tail -3")
print('Errors:', err[:400] if err else 'None')

# Test adding a payment method
pm_test = run("""curl -s -b /tmp/r.txt -X POST 'http://localhost:8080/api/rental/payment-methods' -H 'Content-Type: application/json' -d '{"name":"Test Bank","pm_type":"bank_transfer","account_number":"1234567890","bank_name":"Test Bank","holder_name":"Admin"}'""")
print('PM create:', pm_test[:200])

ssh.close()
