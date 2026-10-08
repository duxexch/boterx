import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

# Create channel_partners.csv if not exists
run = lambda cmd: ssh.exec_command(cmd, timeout=30)[1].read().decode('utf-8', 'ignore').strip()

# Check if file exists
out = run("ls -la /opt/bot/channel_partners.csv 2>/dev/null || echo 'NOT FOUND'")
print("File check:", out)

# Create with header if not exists
run("test -f /opt/bot/channel_partners.csv || echo 'id,channel_name,chat_id,subscriber_count,revenue_share,category,contact,is_active,created_at' > /opt/bot/channel_partners.csv")

# Verify
out = run("cat /opt/bot/channel_partners.csv")
print("CSV content:", out)

ssh.close()