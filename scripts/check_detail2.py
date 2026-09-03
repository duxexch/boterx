import paramiko, sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('69.169.108.197', 22, 'root', 'M12122099m@@@@', timeout=15)

def run(cmd):
    _, stdout, _ = ssh.exec_command(cmd)
    return stdout.read().decode().strip()

detail = run("curl -s 'https://vex.deals/company/1?lang=de'")

# Check script tags
opens = [(m.start(), m.group()[:80]) for m in re.finditer(r'<script[^>]*>', detail)]
closes = [m.start() for m in re.finditer(r'</script>', detail)]
print('Script tags: %d open, %d close' % (len(opens), len(closes)))
for pos, tag in opens:
    line = detail[:pos].count('\n') + 1
    print('  OPEN  line %d: %s' % (line, tag))
for pos in closes:
    line = detail[:pos].count('\n') + 1
    print('  CLOSE line %d' % line)

# Check if I18N_TRANSLATIONS is defined BEFORE applyTranslations is called
i18n_pos = detail.find('window.I18N_TRANSLATIONS')
apply_pos = detail.find('function applyTranslations')
call_pos = detail.find('applyTranslations(companyName)')
print('\nPositions: I18N=%d, applyFunc=%d, applyCall=%d' % (i18n_pos, apply_pos, call_pos))
print('I18N before applyFunc: %s' % (i18n_pos < apply_pos))
print('applyFunc before call: %s' % (apply_pos < call_pos))

# Check for duplicate 'function applyTranslations' (would cause error)
count = detail.count('function applyTranslations')
print('applyTranslations count: %d' % count)

# Check that the I18N block doesn't have the broken truncation issue
# Find comp_desc_1xbet in the detail page I18N
for lang in ['en', 'de', 'fr']:
    idx = detail.find("  %s: {" % lang)
    if idx > 0:
        # Find the next lang block
        next_lang = re.search(r'\n  \w+: \{', detail[idx+5:])
        if next_lang:
            block = detail[idx:idx+next_lang.start()]
            if "comp_desc_1xbet" not in block and lang != 'ar':
                pass  # Not all detail pages have comp_desc keys
            # Check for truncated strings
            for line in block.split('\n'):
                if line.strip().endswith("\\',"):
                    print('TRUNCATED in %s: %s' % (lang, line.strip()[-60:]))

# Most importantly: check if there's a missing comma that breaks the JS
# Find the closing of each lang block
for lang in ['ar', 'en', 'de']:
    marker = "  %s: {" % lang
    idx = detail.find(marker)
    if idx < 0: continue
    # Find footer_copyright line (last key in each block)
    fc = detail.find('footer_copyright:', idx)
    if fc > 0 and fc < idx + 2000:
        # Check what comes after it
        eol = detail.find('\n', fc)
        after = detail[eol+1:eol+5].strip()
        print('%s footer_copyright ends: "%s" -> next: "%s"' % (lang, detail[fc:eol].strip()[-40:], after))

ssh.close()
