"""Find HARDCODED visible text (Arabic or English) NOT wrapped in i18n on key pages."""
import re
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

def run(cmd, timeout=30):
    s, o, e = ssh.exec_command(cmd, timeout=timeout)
    return o.read().decode('utf-8', 'ignore').strip()

run('curl -s -c /tmp/ck.txt "http://127.0.0.1:8080/vex/admin/admin" -d "admin_id=7146701713&password=Vex-LN36X_SG3bv-UNooqkME" -o /dev/null')

# Check templates on server for hardcoded text - scan the actual template files
templates = run("ls /opt/bot/dashboard/templates/*.html").split("\n")
print(f"templates: {len(templates)}")

AR_RE = re.compile(r'[\u0600-\u06FF]{2,}')

report = []
for tpl in templates:
    name = tpl.split("/")[-1]
    if name in ["login.html", "showcase_index.html", "showcase_section.html", "showcase_expired.html", "features_showcase.html"]:
        continue
    src = run(f"cat {tpl}")
    if not src:
        continue
    # Find text nodes with Arabic that are NOT inside x-text/data-i18n attributes
    # Look for >Arabic text< patterns (visible hardcoded text)
    hardcoded = []
    for m in re.finditer(r'>([^<>]*[\u0600-\u06FF][^<>]*)<', src):
        txt = m.group(1).strip()
        # skip if inside a jinja var or pure punctuation
        if txt and len(txt) > 1 and '{{' not in txt and '{%' not in txt:
            # get line number
            line_no = src[:m.start()].count('\n') + 1
            hardcoded.append((line_no, txt[:80]))
    if hardcoded:
        report.append(f"\n=== {name}: {len(hardcoded)} hardcoded Arabic text nodes ===")
        for ln, txt in hardcoded[:40]:
            report.append(f"  L{ln}: {txt}")

with open("hardcoded_report.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(report))
print("done - see hardcoded_report.txt")
ssh.close()