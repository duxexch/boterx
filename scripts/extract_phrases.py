"""Extract UNIQUE hardcoded Arabic phrases from admin templates -> phrases file."""
import re
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

def run(cmd, timeout=30):
    s, o, e = ssh.exec_command(cmd, timeout=timeout)
    return o.read().decode('utf-8', 'ignore').strip()

# Admin-only templates (skip user-facing pages which have own i18n)
ADMIN_TEMPLATES = [
    "base.html", "dashboard.html", "users.html", "transactions.html", "matching.html",
    "agents.html", "trading.html", "svrp.html", "lottery_admin.html", "wheel_admin.html",
    "companies.html", "payment_methods.html", "apps.html", "referrals.html",
    "channels.html", "bots.html", "clients.html", "complaints.html", "broadcast.html",
    "statistics.html", "admin_management.html", "themes.html", "exchange_addresses.html",
    "settings.html", "backup.html", "audit_log.html", "ai_api_keys.html",
    "send_message.html", "tickets.html", "seo.html",
]

# Check which actually exist
existing = run("ls /opt/bot/dashboard/templates/").split("\n")
existing = [x.strip() for x in existing if x.strip()]

phrases = set()
for name in ADMIN_TEMPLATES:
    if name not in existing:
        continue
    src = run(f"cat /opt/bot/dashboard/templates/{name}")
    if not src:
        continue
    # Remove script and style blocks first (avoid JS comments)
    src = re.sub(r'<script[^>]*>.*?</script>', '', src, flags=re.S)
    src = re.sub(r'<style[^>]*>.*?</style>', '', src, flags=re.S)
    # Text nodes with Arabic
    for m in re.finditer(r'>([^<>]*[\u0600-\u06FF][^<>]*)<', src):
        txt = m.group(1).strip()
        if txt and len(txt) > 1 and '{{' not in txt and '{%' not in txt:
            phrases.add(txt)
    # Attribute values with Arabic (placeholder/title/aria-label/value)
    for m in re.finditer(r'(?:placeholder|title|aria-label)="([^"]*[\u0600-\u06FF][^"]*)"', src):
        txt = m.group(1).strip()
        if txt and '{{' not in txt:
            phrases.add(txt)

phrases = sorted(phrases)
with open("ar_phrases.txt", "w", encoding="utf-8") as f:
    for p in phrases:
        f.write(p + "\n")

print(f"unique phrases: {len(phrases)}")
ssh.close()