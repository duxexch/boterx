import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=120)

cmds = [
    '/opt/bot/venv/bin/playwright install chromium 2>&1',
    '/opt/bot/venv/bin/playwright install-deps chromium 2>&1',
]
for cmd in cmds:
    print(f"\n>>> {cmd.split('/')[-1]}")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=300)
    out = stdout.read()
    err = stderr.read()
    print(f"  OUT: {out[-300:].decode('utf-8', errors='replace')}")
    if err.strip():
        print(f"  ERR: {err[-300:].decode('utf-8', errors='replace')}")

# Verify
stdin, stdout, stderr = ssh.exec_command('/opt/bot/venv/bin/python3 -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(headless=True); b.close(); p.stop(); print(OK)"')
print(f"\nVerify: {stdout.read().decode('utf-8', errors='replace').strip()} {stderr.read().decode('utf-8', errors='replace').strip()}")

ssh.close()
