import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=10)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=30)
    return stdout.read().decode('utf-8', errors='replace').strip()

run("""curl -s -c /tmp/r.txt -L -o /dev/null -X POST 'http://localhost:8080/vex/admin/admin' --data-urlencode 'admin_id=7146701713' --data-urlencode 'password=Vex-LN36X_SG3bv-UNooqkME'""")

# Get the rental page HTML and check for broken links/references
out = run("curl -s -b /tmp/r.txt 'http://localhost:8080/rental'")

# Find all href and url_for references
import re
links = re.findall(r'href=[\"\'](/[^\"\']+)', out)
for l in links:
    print(f"Link: {l}")

# Check if page_bots or page_clients is referenced in template
if 'page_bots' in out:
    print("\nWARNING: page_bots referenced in rental.html")
if 'page_clients' in out:
    print("\nWARNING: page_clients referenced in rental.html")

# Check base.html sidebar for what it renders
base = run("curl -s -b /tmp/r.txt 'http://localhost:8080/rental'")
sidebar_links = re.findall(r'href=\"(/(?:clients|bots|rental)[^\"]*?)\"', base)
print(f"\nSidebar client/bot/rental links: {sidebar_links}")

# Check what active_page the user might see
if 'active_page' in out:
    matches = re.findall(r'active_page.*?[\"\'](.*?)[\"\']', out)
    print(f"\nactive_page: {matches}")

# Check if there's a JS redirect to /clients or /bots
redirects = re.findall(r'location\s*(?:\.href|=)\s*[\"\']*/(clients|bots)[\"\']*', out)
print(f"\nJS redirects to /clients or /bots: {redirects}")

ssh.close()
