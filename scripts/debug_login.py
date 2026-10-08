import paramiko, sys, json
sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

def run(cmd, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    return stdout.read().decode('utf-8', 'ignore').strip(), stderr.read().decode('utf-8', 'ignore').strip()

# Check cookie file
run("curl -s -c /tmp/v3.txt -b /tmp/v3.txt 'http://127.0.0.1:8080/vex/admin/admin' -d 'admin_id=7146701713&password=Vex-LN36X_SG3bv-UNooqkME' -v 2>&1 > /tmp/curl_out.txt")

out, _ = run("cat /tmp/curl_out.txt")
print("=== Login response headers ===")
# Find Location header or Set-Cookie
for line in out.split('\n'):
    if 'Location' in line or 'Set-Cookie' in line or 'HTTP/' in line:
        print(line.strip())

out, _ = run("cat /tmp/v3.txt 2>/dev/null || echo 'no cookie file'")
print(f"\n=== Cookie file ===\n{out[:500]}")

# Try manual cookie approach
run("rm -f /tmp/v3.txt")
out, _ = run("curl -s -c /tmp/v3.txt 'http://127.0.0.1:8080/vex/admin/admin' -d 'admin_id=7146701713&password=Vex-LN36X_SG3bv-UNooqkME' -D /tmp/headers.txt")
print(f"\n=== Login response ===\n{out[:300]}")
out, _ = run("cat /tmp/headers.txt")
print(f"\n=== Response headers ===\n{out[:500]}")
out, _ = run("cat /tmp/v3.txt")
print(f"\n=== Cookie jar ===\n{out[:500]}")

# Now try accessing the admin page with cookie
out, _ = run("curl -s -b /tmp/v3.txt 'http://127.0.0.1:8080/vex/admin/admin' -D /tmp/h2.txt")
print(f"\n=== Admin page access ===\nHeaders:")
out2, _ = run("cat /tmp/h2.txt")
print(out2[:300])
out3, _ = run("curl -s -b /tmp/v3.txt 'http://127.0.0.1:8080/vex/admin/admin' | head -5")
print(f"\nBody first lines:\n{out3}")

ssh.close()
