import paramiko, sys, io, subprocess, os, tempfile, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', 22, 'root', 'M12122099m@@@@', timeout=15)

def run(cmd):
    _, stdout, _ = ssh.exec_command(cmd)
    return stdout.read().decode().strip()

detail = run("curl -s 'https://vex.deals/company/1?lang=de'")

# Extract COMPANY_I18N block
ci_start = detail.find('window.COMPANY_I18N = {')
ci_end_marker = '};'
depth = 0
ci_end = -1
for idx in range(ci_start + len('window.COMPANY_I18N = {') - 1, len(detail)):
    if detail[idx] == '{': depth += 1
    elif detail[idx] == '}':
        depth -= 1
        if depth == 0:
            ci_end = idx + 1
            break

ci_obj = detail[ci_start + len('window.COMPANY_I18N = '):ci_end]
print('COMPANY_I18N length: %d chars' % len(ci_obj))

# Check languages
langs = re.findall(r'^\s+(\w+): \{', ci_obj, re.MULTILINE)
print('Languages in COMPANY_I18N:', ', '.join(langs))

# Check for truncated strings
lines = ci_obj.split('\n')
truncated = 0
for i, line in enumerate(lines):
    stripped = line.strip()
    if stripped.endswith("\\',") or stripped.endswith("\\')"):
        print('TRUNCATED line %d: %s' % (i+1, stripped[-80:]))
        truncated += 1
    # Also check for single-quoted strings with unbalanced quotes
    if ": '" in stripped:
        val_start = stripped.find("'")
        val = stripped[val_start:]
        unescaped = 0
        j = 0
        while j < len(val):
            if val[j] == '\\' and j+1 < len(val):
                j += 2
            elif val[j] == "'":
                unescaped += 1
                j += 1
            else:
                j += 1
        if unescaped > 2:
            print('BROKEN QUOTES line %d: %s' % (i+1, stripped[:100]))
            truncated += 1

if truncated == 0:
    print('No truncated/broken strings found')

# Write test JS
test = 'var COMPANY_I18N = ' + ci_obj + ';\n'
test += 'var langs = Object.keys(COMPANY_I18N);\n'
test += 'console.log("Languages: " + langs.join(", "));\n'
test += 'langs.forEach(function(lang) {\n'
test += '  var companies = Object.keys(COMPANY_I18N[lang]);\n'
test += '  companies.forEach(function(c) {\n'
test += '    var d = COMPANY_I18N[lang][c];\n'
test += '    if (!d.desc) console.log("MISSING desc: " + lang + "." + c);\n'
test += '    if (!d.pros) console.log("MISSING pros: " + lang + "." + c);\n'
test += '    if (!d.cons) console.log("MISSING cons: " + lang + "." + c);\n'
test += '  });\n'
test += '});\n'

tmp = os.path.join(tempfile.gettempdir(), 'company_i18n_test.js')
with open(tmp, 'w', encoding='utf-8') as f:
    f.write(test)

result = subprocess.run(['node', tmp], capture_output=True, text=True, timeout=10)
print('\nNode.js test:')
print(result.stdout)
if result.stderr:
    print('ERROR:', result.stderr[:500])

ssh.close()
