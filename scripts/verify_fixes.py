import sys,io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace')
with open('dashboard/templates/landing.html','r',encoding='utf-8') as f:
    content=f.read()
idx=content.find('comp_desc_1xbet')
after=content[idx:idx+500]
if '</span>' in after.split('{% elif')[0]:
    print('OK: 1XBET span closed')
else:
    print('PROBLEM: 1XBET span NOT closed')
idx=content.find('comp_desc_melbet')
after=content[idx:idx+500]
if '</span>' in after.split('{% else')[0]:
    print('OK: MELBET span closed')
else:
    print('PROBLEM: MELBET span NOT closed')
if 'English' in content.split('currentLang')[1][:50]:
    print('OK: currentLang shows English')
else:
    print('PROBLEM: currentLang')
if 'textContent' in content and 'innerHTML' in content:
    print('OK: IIFE has textContent+innerHTML')
count=content.count('placeholder=')
print(f'Placeholder attributes: {count}')
