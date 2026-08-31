import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', username='root', password='M12122099m@@@@', timeout=10)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=30)
    return stdout.read().decode('utf-8', errors='replace').strip()

run("""curl -s -c /tmp/r.txt -L -o /dev/null -X POST 'http://localhost:8080/vex/admin/admin' --data-urlencode 'admin_id=7146701713' --data-urlencode 'password=Vex-LN36X_SG3bv-UNooqkME'""")

html = run("curl -s -b /tmp/r.txt 'http://localhost:8080/rental'")

# Check if app.js is loaded
if 'app.js' in html:
    print("app.js: INCLUDED")
else:
    print("app.js: NOT INCLUDED - THIS IS THE PROBLEM")

# Find all script src tags
import re
scripts = re.findall(r'<script[^>]*src="([^"]+)"', html)
print("\nScript sources:")
for s in scripts:
    print(f"  {s}")

# Check if rental page extends base.html properly
if '{% extends' in html:
    print("\nExtends base: YES")
else:
    print("\nExtends base: checking...")
    if 'rentalSystem' in html and 'function api' in html:
        print("  Has both rentalSystem and api - should work")
    elif 'rentalSystem' in html and 'function api' not in html:
        print("  Has rentalSystem but api() comes from app.js - check if loaded")

# Look for the issue - check if the rentalSystem function has errors
# Find the function
idx = html.find('function rentalSystem()')
if idx > 0:
    # Get just the function
    func_text = html[idx:]
    end = func_text.find('</script>')
    if end > 0:
        func_text = func_text[:end]
    
    # Check bracket balance
    opens = func_text.count('{')
    closes = func_text.count('}')
    print(f"\nrentalSystem brackets: {{ = {opens}, }} = {closes}")
    
    # Check if there are unescaped quotes or template literal issues
    # Check for x-text with t() calls
    t_calls = func_text.count("t('")
    print(f"t() calls in function: {t_calls}")
    
    # Check the I18N dict
    i18n_idx = func_text.find('const I18N')
    if i18n_idx > 0:
        i18n_text = func_text[i18n_idx:i18n_idx+500]
        print(f"\nI18N dict starts: {i18n_text[:200]}")

# Most importantly - check if there's a JavaScript error by looking for unmatched syntax
# Get just the script section
script_start = html.find('<script>')
script_end = html.rfind('</script>')
if script_start > 0 and script_end > script_start:
    script = html[script_start:script_end+9]
    print(f"\nScript length: {len(script)} chars")
    
    # Check for common issues
    issues = []
    if script.count("x-text=\"t('") != script.count("t('"):
        issues.append("t() call count mismatch")
    
    # Check for the specific I18N structure
    if "'ar':" in script and "'en':" in script:
        print("I18N has ar and en: OK")
    
    # Check if the 't' function is defined inside the return
    if "t(key)" in script or "t:" in script:
        print("t() function: FOUND in return object")

ssh.close()
