import sys,io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace')
with open('dashboard/templates/landing.html','r',encoding='utf-8') as f:
    content=f.read()
for line in content.split('\n'):
    if '<html' in line:
        print('HTML tag:', line.strip()[:80])
        break
idx=content.find('(function(){')
iife=content[idx:idx+2000]
print(f'IIFE starts at char {idx}')
if 'window.location.replace' in iife:
    print('WARNING: auto-redirect still exists!')
else:
    print('OK: no auto-redirect')
if "lang='en'" in iife or 'lang="en"' in iife:
    print('OK: default language is English')
else:
    print('Checking default...')
    for line in iife.split('\n'):
        if 'lang' in line and 'en' in line:
            print(f'  {line.strip()[:80]}')
