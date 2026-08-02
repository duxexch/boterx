import paramiko
import sys

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=15)

commands = [
    # 1. Add missing env vars
    "grep -q DASHBOARD_PASSWORD /opt/bot/.env || echo 'DASHBOARD_PASSWORD=boterx_admin_2026' >> /opt/bot/.env",
    "grep -q DASHBOARD_PORT /opt/bot/.env || echo 'DASHBOARD_PORT=8080' >> /opt/bot/.env",
    "grep -q DASHBOARD_HOST /opt/bot/.env || echo 'DASHBOARD_HOST=0.0.0.0' >> /opt/bot/.env",

    # 2. Migrate payment_methods.csv — add currency column
    """cd /opt/bot && python3 -c "
import csv
rows = []
with open('payment_methods.csv', 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    old_fields = reader.fieldnames
    rows = list(reader)

if 'currency' not in old_fields:
    # Add currency column with defaults
    currency_map = {
        'فودافون كاش': 'EGP',
        'حساب بنكي أساسي': 'SAR',
        'محفظة STC': 'SAR',
        'حساب جاري': 'SAR',
    }
    for row in rows:
        name = row.get('method_name', '')
        row['currency'] = currency_map.get(name, '')

    new_fields = list(old_fields) + ['currency']
    with open('payment_methods.csv', 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=new_fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, '') for k in new_fields})
    print('MIGRATED: added currency column')
else:
    print('ALREADY HAS currency column')
" """,

    # 3. Verify migration
    "head -1 /opt/bot/payment_methods.csv",
    "cat /opt/bot/payment_methods.csv | head -5",

    # 4. Restart services
    "systemctl restart boterx",
    "systemctl restart boterx-dashboard",
    "sleep 2",

    # 5. Verify
    "systemctl status boterx --no-pager | head -3",
    "systemctl status boterx-dashboard --no-pager | head -3",

    # 6. Test API with currency
    "curl -s -c /tmp/c4.txt -b /tmp/c4.txt -X POST http://127.0.0.1:8080/login -d 'admin_id=7146701713&password=boterx_admin_2026' -o /dev/null -w '%{http_code}'",
    "curl -s -b /tmp/c4.txt http://127.0.0.1:8080/api/payment-methods",
]

for cmd in commands:
    sys.stdout.buffer.write(f">>> {cmd[:100]}\n".encode('utf-8'))
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read()
    err = stderr.read()
    if out:
        sys.stdout.buffer.write(out[:800])
        sys.stdout.buffer.write(b"\n")
    if err:
        sys.stdout.buffer.write(b"ERR: ")
        sys.stdout.buffer.write(err[:300])
        sys.stdout.buffer.write(b"\n")
    sys.stdout.buffer.write(b"---\n")
    sys.stdout.buffer.flush()

ssh.close()
sys.stdout.buffer.write(b"DONE\n")
