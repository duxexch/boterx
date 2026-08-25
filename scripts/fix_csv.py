import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

# Read current CSV
s, o, e = ssh.exec_command("cat /opt/bot/bot_channels.csv")
csv_content = o.read().decode('utf-8', 'ignore')

# Parse CSV lines
lines = csv_content.strip().split('\n')
if lines and lines[0].startswith('\ufeff'):
    lines[0] = lines[0][1:]  # Remove BOM
header = lines[0]
data_lines = lines[1:]

# Remove duplicates by ID (first column) and skip invalid rows
seen_ids = set()
clean_lines = [header]
for line in data_lines:
    if not line.strip():
        continue
    parts = line.split(',')
    if len(parts) < 2:
        continue
    cid = parts[0].strip()
    if cid == '?id' or cid == 'id':  # Skip header row that got mixed in
        continue
    if cid in seen_ids:
        print(f"Skipping duplicate: {cid}")
        continue
    seen_ids.add(cid)
    clean_lines.append(line)

# Write back
clean_content = '\n'.join(clean_lines)
import tempfile
with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv', encoding='utf-8') as tf:
    tf.write(clean_content)
    temp_path = tf.name

# Upload fixed CSV
sftp = ssh.open_sftp()
sftp.put(temp_path, '/opt/bot/bot_channels.csv')
import os
os.unlink(temp_path)
sftp.close()

# Verify
s, o, e = ssh.exec_command("cat /opt/bot/bot_channels.csv | cut -d',' -f1 | sort | uniq -c | sort -nr | head -5")
print(o.read().decode('utf-8', 'ignore').strip())

ssh.close()
print("CSV fixed!")