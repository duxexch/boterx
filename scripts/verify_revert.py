import paramiko, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

# Check if bridge files still exist on server
stdin, stdout, stderr = ssh.exec_command("ls -lh /opt/bot/dashboard/templates/bridge.html 2>&1; ls -lh /opt/bot/company_transfers.csv 2>&1", timeout=10)
print(stdout.read().decode('utf-8','ignore'))

# Check if route still exists
stdin, stdout, stderr = ssh.exec_command("grep -n 'bridge\\|company_transfers' /opt/bot/dashboard/app.py | head -20", timeout=10)
print(stdout.read().decode('utf-8','ignore'))

# Test /go/1 should now be campaign or 404
stdin, stdout, stderr = ssh.exec_command("curl -sk -o /dev/null -w 'go/1: %{http_code}' 'https://vex.deals/go/1' 2>/dev/null", timeout=10)
print(stdout.read().decode('utf-8','ignore').strip())

# Test bot still has direct link
stdin, stdout, stderr = ssh.exec_command("grep -A2 'فتح المشروع' /opt/bot/comprehensive_bot.py | head -10", timeout=10)
out = stdout.read().decode('utf-8','ignore')
print("bot bridge:", "found" if "bridge" in out.lower() or "vex.deals/go" in out else "not found (reverted)")

ssh.close()
