import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=30)

def run(cmd, timeout=30):
    s, o, e = ssh.exec_command(cmd, timeout=timeout)
    return o.read().decode('utf-8', 'ignore').strip()

# Which admin templates do NOT extend base.html
out = run("""for f in /opt/bot/dashboard/templates/*.html; do
  if ! grep -q "extends 'base.html'" "$f" && ! grep -q 'extends "base.html"' "$f"; then
    echo "$(basename $f)";
  fi;
done""")
with open("no_base_templates.txt", "w", encoding="utf-8") as f:
    f.write(out)
print(out)

# Python error context
err = run("journalctl -u boterx-dashboard.service --since '10 minutes ago' --no-pager | grep -B5 -A15 \"not supported between\"")
with open("py_error.txt", "w", encoding="utf-8") as f:
    f.write(err)
print("\n=== python error (last 60 lines) ===")
print("\n".join(err.split("\n")[-40:]))

ssh.close()