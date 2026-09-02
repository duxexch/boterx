import sys, io, requests
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Check English
r = requests.get('https://vex.deals/?lang=en', verify=False, timeout=15)
html = r.text
checks = ['Browse Companies', 'My Web Games', 'Best Licensed Companies', 'Promo Code', 'Register at', 'Download App', 'Verified Partner', 'How to Start', 'FAQ', 'Play Responsibly']
print(f'EN page: status={r.status_code}, len={len(html)}')
for c in checks:
    status = 'OK' if c in html else 'MISSING'
    print(f'  {status}: {c}')

# Check German
r2 = requests.get('https://vex.deals/?lang=de', verify=False, timeout=15)
html2 = r2.text
de_checks = ['Unternehmen Durchsuchen', 'Meine Web-Spiele', 'Lizenz', 'Promo-Code', 'Registrieren bei', 'Code Kopieren', 'Verifizierter Partner']
print(f'\nDE page: status={r2.status_code}, len={len(html2)}')
for c in de_checks:
    status = 'OK' if c in html2 else 'MISSING'
    print(f'  {status}: {c}')

# Check Russian
r3 = requests.get('https://vex.deals/?lang=ru', verify=False, timeout=15)
html3 = r3.text
ru_checks = ['\u0421\u043c\u043e\u0442\u0440\u0435\u0442\u044c \u041a\u043e\u043c\u043f\u0430\u043d\u0438\u0438', '\u041f\u0440\u043e\u043c\u043e\u043a\u043e\u0434', '\u0417\u0430\u0440\u0435\u0433\u0438\u0441\u0442\u0440\u0438\u0440\u043e\u0432\u0430\u0442\u044c\u0441\u044f \u0432']
print(f'\nRU page: status={r3.status_code}, len={len(html3)}')
for c in ru_checks:
    status = 'OK' if c in html3 else 'MISSING'
    print(f'  {status}: {c}')

# Check company detail
r4 = requests.get('https://vex.deals/company/1xbet?lang=en', verify=False, timeout=15)
html4 = r4.text
cd_checks = ['Back to Home', 'Copy Code', 'Download App', 'Overview', 'Company Details', 'Pros', 'Cons', 'Similar Companies', 'Verified Partner']
print(f'\nCompany detail EN: status={r4.status_code}, len={len(html4)}')
for c in cd_checks:
    status = 'OK' if c in html4 else 'MISSING'
    print(f'  {status}: {c}')
