import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

def run(cmd, timeout=30):
    s, o, e = ssh.exec_command(cmd, timeout=timeout)
    return o.read().decode('utf-8', 'ignore').strip()

# Login
run('curl -s -c /tmp/ck.txt "http://127.0.0.1:8080/vex/admin/admin" -d "admin_id=7146701713&password=Vex-LN36X_SG3bv-UNooqkME" -o /dev/null')

# Test endpoints
endpoints = [
    "/api/partners",
    "/api/ad-net",
    "/api/channel-groups",
    "/api/ai-providers",
    "/api/ai-agents",
    "/api/platform-accounts",
    "/api/source-channels",
    "/api/channels/daily-report",
    "/api/text-replacements",
    "/api/post-vault",
    "/api/relay-log",
    "/api/campaigns",
    "/api/campaigns/analytics",
    "/api/partners",
    "/api/ad-net",
]

for ep in endpoints:
    out = run(f"curl -s -b /tmp/ck.txt -w '\nHTTP:%{{http_code}}' http://127.0.0.1:8080{ep}")
    print(f"{ep}: {out.split('HTTP:')[-1]}")

ssh.close()