import paramiko, sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

# Create a test transfer directly via python
cmd = """
python3 -c "
import csv, os, time, secrets
BASE_DIR='/opt/bot'
# Find a real user
with open('/opt/bot/users.csv','r',encoding='utf-8-sig') as f:
    import csv
    r=list(csv.DictReader(f))
    # pick first non-admin with balance?
    for u in r:
        if u['telegram_id'] not in ('7146701713',):
            print(u['telegram_id'], u['name'], u['customer_id'])
            break

# Create a test transfer for that user
from dashboard.app import read_csv, write_csv, append_csv, BASE_DIR
import dashboard.app as app
# manually create entry
fields=['id','user_id','customer_id','company_id','company_name','company_account','amount','currency','status','created_at','processed_at','processed_by','admin_note','affiliate_link_snapshot']
with open(os.path.join(BASE_DIR,'company_transfers.csv'),'r',encoding='utf-8-sig') as f:
    rows=list(csv.DictReader(f))
print('existing', len(rows))
"
"""
stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
print(stdout.read().decode('utf-8','ignore'))
print(stderr.read().decode('utf-8','ignore'))

# Test the wallet bridge with real user via webapp auth simulation
# Use initData? Simpler: test the bridge page loads correctly with company data
stdin, stdout, stderr = ssh.exec_command("curl -sk 'https://vex.deals/go/1' 2>/dev/null | grep -c 'bridge-topbar'", timeout=10)
print("bridge topbar count:", stdout.read().decode('utf-8','ignore').strip())

stdin, stdout, stderr = ssh.exec_command("curl -sk 'https://vex.deals/go/1' 2>/dev/null | grep -c 'transfer-card'", timeout=10)
print("transfer card:", stdout.read().decode('utf-8','ignore').strip())

# Test the wallet link now points to /go
stdin, stdout, stderr = ssh.exec_command("curl -sk -c /tmp/br4.txt -X POST 'https://vex.deals/vex/admin/admin' -H 'Content-Type: application/x-www-form-urlencoded' -d 'admin_id=7146701713&password=Vex-LN36X_SG3bv-UNooqkME' -o /dev/null", timeout=10)
stdin.read()
import time; time.sleep(1)
stdin, stdout, stderr = ssh.exec_command("curl -sk -b /tmp/br4.txt 'https://vex.deals/wallet' 2>/dev/null | grep -c '/go/'", timeout=10)
print("wallet has /go links:", stdout.read().decode('utf-8','ignore').strip())

ssh.close()
