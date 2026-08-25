import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

def run(cmd, timeout=20):
    s, o, e = ssh.exec_command(cmd, timeout=timeout)
    return o.read().decode('utf-8', 'ignore').strip()

# Restart once more to ensure the key got generated at boot (it generates on startup)
key = run("grep '^HERMES_API_KEY=' /opt/bot/.env | cut -d= -f2")
if not key:
    run("systemctl restart boterx-dashboard.service")
    import time
    time.sleep(15)
    key = run("grep '^HERMES_API_KEY=' /opt/bot/.env | cut -d= -f2")

with open("hermes_key.txt", "w", encoding="utf-8") as f:
    f.write(key)

# Test: ping without key (expect 401), with key (expect ok), stats with key
tests = []
tests.append(("no key", run("curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/api/v1/ping")))
tests.append(("ping with key", run(f"curl -s http://127.0.0.1:8080/api/v1/ping -H 'X-API-Key: {key}'")))
tests.append(("stats with key", run(f"curl -s -o /dev/null -w '%{{http_code}}' http://127.0.0.1:8080/api/stats -H 'X-API-Key: {key}'")))
tests.append(("users with key", run(f"curl -s -o /dev/null -w '%{{http_code}}' 'http://127.0.0.1:8080/api/users?limit=2' -H 'X-API-Key: {key}'")))
tests.append(("complaints with key", run(f"curl -s -o /dev/null -w '%{{http_code}}' http://127.0.0.1:8080/api/complaints -H 'X-API-Key: {key}'")))
tests.append(("wrong key", run("curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/api/v1/ping -H 'X-API-Key: wrong'")))

with open("hermes_test.txt", "w", encoding="utf-8") as f:
    for name, res in tests:
        f.write(f"{name}: {res}\n")

print("key saved to hermes_key.txt, tests in hermes_test.txt")
ssh.close()