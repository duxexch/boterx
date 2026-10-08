import paramiko, sys, io, subprocess, os, tempfile, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', 22, 'root', 'M12122099m@@@@', timeout=15)

def run(cmd):
    _, stdout, _ = ssh.exec_command(cmd)
    return stdout.read().decode().strip()

# Get detail page for 1XBET in German
detail = run("curl -s 'https://vex.deals/company/1?lang=de'")
print('Detail page size: %d' % len(detail))

# Check key elements
checks = [
    ('I18N_TRANSLATIONS', 'window.I18N_TRANSLATIONS' in detail),
    ('applyTranslations', 'function applyTranslations' in detail),
    ('COMPANY_I18N', 'window.COMPANY_I18N' in detail),
    ('data-i18n', 'data-i18n=' in detail),
]
for name, found in checks:
    print('  %s: %s' % (name, 'YES' if found else 'NO'))

# Extract the I18N block and validate
start = detail.find('window.I18N_TRANSLATIONS = {')
if start > 0:
    depth = 0
    end = -1
    for idx in range(start + len('window.I18N_TRANSLATIONS = {') - 1, len(detail)):
        if detail[idx] == '{': depth += 1
        elif detail[idx] == '}':
            depth -= 1
            if depth == 0:
                end = idx + 1
                break
    i18n_obj = detail[start + len('window.I18N_TRANSLATIONS = '):end]
    print('I18N object length: %d chars' % len(i18n_obj))
    
    # Check languages
    langs = re.findall(r'^\s+(\w+): \{', i18n_obj, re.MULTILINE)
    print('Languages in detail I18N:', ', '.join(langs))
    
    # Write test file
    test = 'var I18N = ' + i18n_obj + ';\nprint("langs: " + Object.keys(I18N).join(","));\n'
    tmp = os.path.join(tempfile.gettempdir(), 'detail_i18n.js')
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(test)
    result = subprocess.run(['node', '--check', tmp], capture_output=True, text=True, timeout=5)
    if result.returncode == 0:
        print('I18N block: VALID JS')
    else:
        print('I18N block: JS ERROR!')
        print(result.stderr[:500])
else:
    print('ERROR: I18N block not found')
    # Check if there's a different issue
    if '</script>' in detail:
        print('</script> found')
        script_parts = detail.split('</script>')
        print('Script blocks: %d' % len(script_parts))

# Check if COMPANY_I18N exists
ci_start = detail.find('window.COMPANY_I18N')
if ci_start > 0:
    print('\nCOMPANY_I18N found at char %d' % ci_start)
else:
    print('\nCOMPANY_I18N NOT found')

# Check if applyTranslations exists
at_start = detail.find('function applyTranslations')
if at_start > 0:
    print('applyTranslations found at char %d' % at_start)
else:
    print('applyTranslations NOT found')

ssh.close()
