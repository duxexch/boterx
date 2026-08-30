import paramiko, json, sys, re, time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=10)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=30)
    return stdout.read().decode('utf-8', errors='replace').strip()

def run_err(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=30)
    return stderr.read().decode('utf-8', errors='replace').strip()

# Step 1: Login as admin and get session cookie
print('=== Step 1: Admin Login ===')
# Use curl -c to save cookies, -L to follow redirects
login_out = run("""curl -s -c /tmp/admin_cookies.txt -L -o /dev/null -w '%{http_code}' \\
  -X POST http://localhost:8080/vex/admin/admin \\
  -d 'admin_id=7146701713&password=Vex-LN36X_SG3bv-UNooqkME'""")
print(f'Login HTTP: {login_out}')

# Verify cookie was saved
cookie_check = run('cat /tmp/admin_cookies.txt 2>&1')
print(f'Cookie file: {cookie_check[:200]}')

# Test 1: Admin center page with session cookie
print('\n=== Test 1: Admin Center Page ===')
code = run("curl -s -b /tmp/admin_cookies.txt -o /dev/null -w '%{http_code}' http://localhost:8080/admin-center")
print(f'HTTP status: {code}')

# Test 2: Admin center API - list admins
print('\n=== Test 2: Admin Center - Admins List ===')
resp = run('curl -s -b /tmp/admin_cookies.txt http://localhost:8080/api/admin-center/admins')
try:
    data = json.loads(resp)
    admins = data.get('admins', [])
    tenants = data.get('tenants', {})
    print(f'Found {len(admins)} admins, {len(tenants)} tenants')
    for a in admins[:5]:
        print(f"  - {a['telegram_id']}: {a['role']} ({a['source']}) tenant={a.get('tenant_id','')}")
except Exception as e:
    print(f'Parse error: {e}')
    print(f'Raw: {resp[:500]}')

# Test 3: Admin center revenue
print('\n=== Test 3: Admin Center - Revenue ===')
resp = run('curl -s -b /tmp/admin_cookies.txt http://localhost:8080/api/admin-center/revenue')
try:
    data = json.loads(resp)
    print('Stats:', json.dumps(data.get('stats', {}), indent=2))
    print(f"By client: {len(data.get('by_client', []))} clients")
except Exception as e:
    print(f'Parse error: {e}')
    print(f'Raw: {resp[:500]}')

# Test 4: Admin center audit
print('\n=== Test 4: Admin Center - Audit ===')
resp = run('curl -s -b /tmp/admin_cookies.txt http://localhost:8080/api/admin-center/audit')
try:
    data = json.loads(resp)
    print(f"Found {len(data.get('logs', []))} audit entries")
    for log in data.get('logs', [])[:3]:
        print(f"  - {log.get('action','')}: {log.get('details','')} @ {log.get('timestamp','')}")
except Exception as e:
    print(f'Parse error: {e}')
    print(f'Raw: {resp[:500]}')

# Test 5: Create a new client
print('\n=== Test 5: Create Client ===')
resp = run("""curl -s -b /tmp/admin_cookies.txt -X POST http://localhost:8080/api/clients \\
  -H 'Content-Type: application/json' \\
  -d '{"name":"Test Agency","bot_username":"TestAgencyBot","bot_token":"7890123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ_test_token","dash_username":"testadmin","dash_password":"Test123456","features":["deposit","withdraw","games","broadcast"],"subscription_days":30,"contact":"@testagency","admin_ids":"123456789","notes":"Test client","revenue_share":40}'""")
try:
    data = json.loads(resp)
    print(json.dumps(data, indent=2, ensure_ascii=False))
    if data.get('success'):
        client_id = data['client']['id']
        print(f'Client ID: {client_id}')
    else:
        print('FAILED to create client')
        client_id = None
except Exception as e:
    print(f'Parse error: {e}')
    print(f'Raw: {resp[:500]}')
    client_id = None

if client_id:
    # Test 6: List clients
    print('\n=== Test 6: List Clients ===')
    resp = run('curl -s -b /tmp/admin_cookies.txt http://localhost:8080/api/clients')
    try:
        data = json.loads(resp)
        print(f"Total clients: {len(data.get('clients', []))}")
        for c in data.get('clients', []):
            print(f"  - {c['id']}: {c['name']} rev={c.get('revenue_share', 'N/A')}% running={c.get('running', False)}")
    except Exception as e:
        print(f'Parse error: {e}')
        print(f'Raw: {resp[:300]}')

    # Test 7: Client dashboard login
    print('\n=== Test 7: Client Dashboard Login ===')
    resp = run(f"""curl -s -c /tmp/client_cookies.txt -b /tmp/client_cookies.txt \\
      -X POST http://localhost:8080/api/client/login \\
      -H 'Content-Type: application/json' \\
      -d '{{"username":"testadmin","password":"Test123456"}}'""")
    try:
        data = json.loads(resp)
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f'Parse error: {e}')
        print(f'Raw: {resp[:500]}')

    # Test 8: Client dashboard page
    print('\n=== Test 8: Client Dashboard Page ===')
    code = run("curl -s -b /tmp/client_cookies.txt -o /dev/null -w '%{http_code}' http://localhost:8080/home")
    print(f'Client dashboard HTTP: {code}')

    # Test 9: Try starting client bot
    print('\n=== Test 9: Start Client Bot ===')
    resp = run(f"curl -s -b /tmp/admin_cookies.txt -X POST http://localhost:8080/api/clients/{client_id}/start -H 'Content-Type: application/json' -d '{{}}'")
    try:
        data = json.loads(resp)
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f'Parse error: {e}')
        print(f'Raw: {resp[:500]}')

    time.sleep(3)

    # Test 10: Check bot process
    print('\n=== Test 10: Check Bot Process ===')
    resp = run(f'ps aux | grep -i "{client_id}" | grep -v grep')
    print(f'Process: {resp[:300] if resp else "Not found"}')

    # Also check if it shows running
    resp2 = run('curl -s -b /tmp/admin_cookies.txt http://localhost:8080/api/clients')
    try:
        data = json.loads(resp2)
        for c in data.get('clients', []):
            if c['id'] == client_id:
                print(f"Running status: {c.get('running', 'N/A')}")
    except:
        pass

    # Test 11: Stop client bot
    print('\n=== Test 11: Stop Client Bot ===')
    resp = run(f"curl -s -b /tmp/admin_cookies.txt -X POST http://localhost:8080/api/clients/{client_id}/stop -H 'Content-Type: application/json' -d '{{}}'")
    try:
        data = json.loads(resp)
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f'Parse error: {e}')
        print(f'Raw: {resp[:500]}')

    # Test 12: Update revenue share
    print('\n=== Test 12: Update Revenue Share ===')
    resp = run(f"curl -s -b /tmp/admin_cookies.txt -X POST http://localhost:8080/api/clients/{client_id} -H 'Content-Type: application/json' -d '{{\"revenue_share\":50}}'")
    try:
        data = json.loads(resp)
        if data.get('client'):
            print(f"Updated revenue share: {data['client'].get('revenue_share', 'N/A')}%")
        else:
            print(json.dumps(data, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f'Parse error: {e}')
        print(f'Raw: {resp[:500]}')

    # Test 13: Suspend client
    print('\n=== Test 13: Suspend Client ===')
    resp = run(f"curl -s -b /tmp/admin_cookies.txt -X POST http://localhost:8080/api/clients/{client_id}/suspend -H 'Content-Type: application/json' -d '{{}}'")
    try:
        data = json.loads(resp)
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f'Parse error: {e}')
        print(f'Raw: {resp[:500]}')

    # Test 14: Activate client
    print('\n=== Test 14: Activate Client ===')
    resp = run(f"curl -s -b /tmp/admin_cookies.txt -X POST http://localhost:8080/api/clients/{client_id}/activate -H 'Content-Type: application/json' -d '{{}}'")
    try:
        data = json.loads(resp)
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f'Parse error: {e}')
        print(f'Raw: {resp[:500]}')

    # Test 15: Add admin via admin center
    print('\n=== Test 15: Add Admin via Admin Center ===')
    resp = run(f"""curl -s -b /tmp/admin_cookies.txt -X POST http://localhost:8080/api/admin-center/admins \\
      -H 'Content-Type: application/json' \\
      -d '{{"telegram_id":"999888777","name":"Test Support Admin","role":"support","type":"permanent","tenant_id":"{client_id}","description":"Support for test client"}}'""")
    try:
        data = json.loads(resp)
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f'Parse error: {e}')
        print(f'Raw: {resp[:500]}')

    # Test 16: Verify admin in list
    print('\n=== Test 16: Verify Admin Added ===')
    resp = run('curl -s -b /tmp/admin_cookies.txt http://localhost:8080/api/admin-center/admins')
    try:
        data = json.loads(resp)
        for a in data.get('admins', []):
            if a['telegram_id'] == '999888777':
                print(f"Found: {a['name']} role={a['role']} tenant={a.get('tenant_id','')}")
                break
        else:
            print('Admin not found in list')
    except Exception as e:
        print(f'Parse error: {e}')

    # Test 17: Delete test admin
    print('\n=== Test 17: Delete Admin ===')
    resp = run("curl -s -b /tmp/admin_cookies.txt -X DELETE http://localhost:8080/api/admin-center/admins/999888777")
    try:
        data = json.loads(resp)
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f'Parse error: {e}')
        print(f'Raw: {resp[:500]}')

    # Test 18: Revenue breakdown
    print('\n=== Test 18: Revenue Dashboard ===')
    resp = run('curl -s -b /tmp/admin_cookies.txt http://localhost:8080/api/admin-center/revenue')
    try:
        data = json.loads(resp)
        for c in data.get('by_client', []):
            print(f"  {c['client_name']}: profit={c['total_profit']} share={c['revenue_share']}% admin={c['admin_amount']} client={c['client_amount']}")
        if not data.get('by_client'):
            print('No clients in revenue breakdown')
    except Exception as e:
        print(f'Parse error: {e}')

    # Test 19: Delete test client
    print('\n=== Test 19: Delete Test Client ===')
    resp = run(f"curl -s -b /tmp/admin_cookies.txt -X DELETE 'http://localhost:8080/api/clients/{client_id}?keep_data=0'")
    try:
        data = json.loads(resp)
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f'Parse error: {e}')
        print(f'Raw: {resp[:500]}')

    # Test 20: Verify deletion
    print('\n=== Test 20: Verify Deletion ===')
    resp = run('curl -s -b /tmp/admin_cookies.txt http://localhost:8080/api/clients')
    try:
        data = json.loads(resp)
        remaining = [c for c in data.get('clients', []) if c.get('name') == 'Test Agency']
        print(f'Test Agency clients remaining: {len(remaining)}')
    except Exception as e:
        print(f'Parse error: {e}')

ssh.close()
print('\n\n=== ALL TESTS COMPLETE ===')
