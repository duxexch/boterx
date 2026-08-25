"""Extract ALL i18n keys used across admin pages + hardcoded text, compare with I18N dict."""
import re
import json
import paramiko
from collections import defaultdict

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

def run(cmd, timeout=30):
    s, o, e = ssh.exec_command(cmd, timeout=timeout)
    return o.read().decode('utf-8', 'ignore').strip()

# Login
run('curl -s -c /tmp/ck.txt "http://127.0.0.1:8080/vex/admin/admin" -d "admin_id=7146701713&password=Vex-LN36X_SG3bv-UNooqkME" -o /dev/null')

# All admin pages
pages = ["/dashboard", "/users", "/transactions", "/matching", "/agents", "/trading",
         "/svrp", "/lottery", "/wheel", "/companies", "/payment-methods", "/apps",
         "/games-admin", "/referrals", "/channels", "/bots", "/clients", "/complaints",
         "/broadcast", "/statistics", "/admins", "/themes", "/exchange-addresses",
         "/settings", "/backup", "/audit-log", "/ai-api-keys"]

used_keys = defaultdict(set)   # key -> set of pages
for pg in pages:
    html = run(f'curl -s -b /tmp/ck.txt "http://127.0.0.1:8080{pg}"')
    if not html or '<html' not in html.lower():
        continue
    for m in re.findall(r"x-text=\"t\\('([^']+)'\\)\"", html):
        used_keys[m].add(pg)
    for m in re.findall(r'data-i18n="([^"]+)"', html):
        used_keys[m].add(pg)
    for m in re.findall(r'data-i18n-placeholder="([^"]+)"', html):
        used_keys[m].add(pg)
    for m in re.findall(r'data-i18n-title="([^"]+)"', html):
        used_keys[m].add(pg)
    # :placeholder="t('...')"
    for m in re.findall(r":placeholder=\"t\\('([^']+)'\\)\"", html):
        used_keys[m].add(pg)
    # x-text="t(&quot;...&quot;)" or double quotes
    for m in re.findall(r'x-text="t\\(&quot;([^&]+)&quot;\\)"', html):
        used_keys[m].add(pg)

# Get I18N dict keys from app.js (both ar and en sections)
app_js = run("cat /opt/bot/dashboard/static/js/app.js")
# ar section starts at 'const I18N = {' ar: { ... en: { ... }
ar_match = re.search(r'const I18N = \{\s*ar: \{(.*?)\n    \},\s*en: \{', app_js, re.S)
en_match = re.search(r'en: \{(.*?)\n    \}\s*\};', app_js, re.S)

def extract_keys(section):
    keys = set()
    for m in re.findall(r"([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*'", section):
        keys.add(m)
    return keys

ar_keys = extract_keys(ar_match.group(1)) if ar_match else set()
en_keys = extract_keys(en_match.group(1)) if en_match else set()

# Also keys used from JS files (t('...') calls)
for jsf in ['app.js', 'base-app.js']:
    js = run(f"cat /opt/bot/dashboard/static/js/{jsf}")
    for m in re.findall(r"t\\('([a-zA-Z_][a-zA-Z0-9_]*)'\\)", js):
        used_keys[m].add(f"js:{jsf}")

missing_in_ar = sorted(k for k in used_keys if k not in ar_keys)
missing_in_en = sorted(k for k in used_keys if k not in en_keys)

report = []
report.append(f"=== TOTAL KEYS USED: {len(used_keys)} ===")
report.append(f"=== AR dict keys: {len(ar_keys)} | EN dict keys: {len(en_keys)} ===")
report.append(f"\n=== MISSING IN AR ({len(missing_in_ar)}) ===")
for k in missing_in_ar:
    report.append(f"  {k}  <- {sorted(used_keys[k])[:3]}")
report.append(f"\n=== MISSING IN EN ({len(missing_in_en)}) ===")
for k in missing_in_en:
    report.append(f"  {k}  <- {sorted(used_keys[k])[:3]}")

with open("i18n_missing_report.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(report))

print(f"keys used: {len(used_keys)}, missing ar: {len(missing_in_ar)}, missing en: {len(missing_in_en)}")
ssh.close()