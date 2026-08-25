import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

def run(cmd, timeout=30):
    s, o, e = ssh.exec_command(cmd, timeout=timeout)
    return o.read().decode('utf-8', 'ignore').strip()

# Check CSV content
out = run("cat /opt/bot/bot_channels.csv | head -5")
with open("csv_head.txt", "w", encoding="utf-8") as f:
    f.write(out)

# Check all IDs
out = run("cat /opt/bot/bot_channels.csv | cut -d',' -f1 | sort | uniq -c | sort -nr | head -20")
with open("csv_ids.txt", "w", encoding="utf-8") as f:
    f.write(out)

print("done")
ssh.close()