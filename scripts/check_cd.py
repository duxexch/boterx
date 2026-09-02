import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
with open('dashboard/templates/company_detail.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Check for hardcoded text in company_detail.html
checks = [
    ('title', content.find('<title>')),
    ('meta_desc', content.find('name="description"')),
]
for name, idx in checks:
    if idx >= 0:
        print(f'{name}: {repr(content[idx:idx+120])}')

# Check for hardcoded Arabic outside data-i18n
lines = content.split('\n')
for i, line in enumerate(lines):
    if 'نجوم' in line and 'data-i18n' not in line:
        print(f'Line {i+1}: {line.strip()[:100]}')
