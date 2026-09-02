import paramiko, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

import time
# Login
stdin, stdout, stderr = ssh.exec_command("curl -sk -c /tmp/br.txt -X POST 'https://vex.deals/vex/admin/admin' -H 'Content-Type: application/x-www-form-urlencoded' -d 'admin_id=7146701713&password=Vex-LN36X_SG3bv-UNooqkME' -o /dev/null -w '%{http_code}'", timeout=10)
print("Login:", stdout.read().decode('utf-8','ignore').strip())
time.sleep(1)

# Test bridge page with a real company
stdin, stdout, stderr = ssh.exec_command("curl -sk 'https://vex.deals/api/companies' -b /tmp/br.txt 2>/dev/null | python3 -c \"import sys,json; d=json.load(sys.stdin); cs=d.get('companies',[]); print(f'companies:{len(cs)}'); [print(c['id'], c['name']) for c in cs[:2]]\"", timeout=10)
out = stdout.read().decode('utf-8','ignore')
print(out)
# Get first company id
stdin, stdout, stderr = ssh.exec_command("curl -sk 'https://vex.deals/api/companies' -b /tmp/br.txt 2>/dev/null | python3 -c \"import sys,json; d=json.load(sys.stdin); cs=d.get('companies',[]); print(cs[0]['id'] if cs else 'none')\"", timeout=10)
cid = stdout.read().decode('utf-8','ignore').strip()
print(f"Test CID: {cid}")

# Test bridge page
stdin, stdout, stderr = ssh.exec_command(f"curl -sk 'https://vex.deals/c/{cid}' -o /dev/null -w 'bridge: %{{http_code}} size=%{{size_download}}'", timeout=10)
print(stdout.read().decode('utf-8','ignore').strip())

# Test bridge not found
stdin, stdout, stderr = ssh.exec_command("curl -sk 'https://vex.deals/c/NONEXIST' -o /dev/null -w 'notfound: %{http_code}'", timeout=10)
print(stdout.read().decode('utf-8','ignore').strip())

# Test company-transfers admin page
stdin, stdout, stderr = ssh.exec_command("curl -sk -b /tmp/br.txt 'https://vex.deals/company-transfers' -o /dev/null -w 'admin page: %{http_code}'", timeout=10)
print(stdout.read().decode('utf-8','ignore').strip())

# Test APIs
stdin, stdout, stderr = ssh.exec_command("curl -sk -b /tmp/br.txt 'https://vex.deals/api/admin/company-transfers' 2>/dev/null | head -c 200", timeout=10)
print(f"admin API: {stdout.read().decode('utf-8','ignore')[:200]}")

# Test click
stdin, stdout, stderr = ssh.exec_command(f"curl -sk -X POST 'https://vex.deals/api/company/click' -H 'Content-Type: application/json' -d '{{\"company_id\":\"{cid}\"}}' 2>/dev/null", timeout=10)
print(f"click: {stdout.read().decode('utf-8','ignore').strip()}")

# Check CSV created
stdin, stdout, stderr = ssh.exec_command("ls -lh /opt/bot/company_*.csv 2>/dev/null; cat /opt/bot/company_clicks.csv 2>/dev/null | head -2", timeout=10)
print(f"CSVs:\n{stdout.read().decode('utf-8','ignore').strip()}")

ssh.close()
