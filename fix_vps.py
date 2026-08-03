import paramiko
import sys

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=15)

# Add sample gifts + restart
commands = [
    # Add sample gifts to wheel_gifts.csv
    """cd /opt/bot && python3 -c "
import csv
gifts = [
    ['GIFT001', 'هدية 50 ريال', 'https://example.com/register?ref=gift50', 'yes', '2026-08-03 00:00'],
    ['GIFT002', 'هدية 100 ريال', 'https://example.com/register?ref=gift100', 'yes', '2026-08-03 00:00'],
    ['GIFT003', 'دورة مجانية', 'https://example.com/register?ref=freespin', 'yes', '2026-08-03 00:00'],
    ['GIFT004', 'خصم 20%', 'https://example.com/register?ref=discount20', 'yes', '2026-08-03 00:00'],
    ['GIFT005', 'جائزة مفاجئة', 'https://example.com/register?ref=surprise', 'yes', '2026-08-03 00:00'],
]
with open('wheel_gifts.csv', 'w', newline='', encoding='utf-8-sig') as f:
    writer = csv.writer(f)
    writer.writerow(['id', 'gift_text', 'affiliate_link', 'is_active', 'created_at'])
    for g in gifts:
        writer.writerow(g)
print('Added 5 gifts')
" """,
    # Verify
    "cat /opt/bot/wheel_gifts.csv",
    # Restart bot
    "systemctl restart boterx",
    "sleep 2",
    "systemctl status boterx --no-pager | head -3",
]

for cmd in commands:
    sys.stdout.buffer.write(f">>> {cmd[:80]}\n".encode('utf-8'))
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read()
    err = stderr.read()
    if out:
        sys.stdout.buffer.write(out[:600])
        sys.stdout.buffer.write(b"\n")
    if err:
        sys.stdout.buffer.write(b"ERR: ")
        sys.stdout.buffer.write(err[:300])
        sys.stdout.buffer.write(b"\n")
    sys.stdout.buffer.write(b"---\n")
    sys.stdout.buffer.flush()

ssh.close()
sys.stdout.buffer.write(b"DONE\n")
