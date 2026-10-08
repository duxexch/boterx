import re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

path = r'C:\Users\gnz\Downloads\boterx-dev\dashboard\templates\landing.html'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix duplicate data-i18n attributes
content = content.replace('data-i18n="nav_games" data-i18n="nav_games"', 'data-i18n="nav_games"')
content = content.replace('data-i18n="nav_login" data-i18n="nav_login"', 'data-i18n="nav_login"')
content = content.replace('data-i18n="nav_companies" data-i18n="nav_companies"', 'data-i18n="nav_companies"')

# Fix broken step2_desc div
content = content.replace('<div class="step-desc"> data-i18n="step2_desc">', '<div class="step-desc" data-i18n="step2_desc">')

# Fix broken FAQ answer divs
content = content.replace('<div> data-i18n="faq_a1">', '<div data-i18n="faq_a1">')
content = content.replace('<div> data-i18n="faq_a2">', '<div data-i18n="faq_a2">')
content = content.replace('<div> data-i18n="faq_a3">', '<div data-i18n="faq_a3">')
content = content.replace('<div> data-i18n="faq_a4">', '<div data-i18n="faq_a4">')

# Fix double data-i18n on vex_license row
content = content.replace('data-i18n="comp_license" data-i18n="vex_license"', 'data-i18n="vex_license"')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Check for remaining duplicate data-i18n
import re
dups = re.findall(r'data-i18n="[^"]*"\s+data-i18n=', content)
print(f"Duplicate data-i18n found: {len(dups)}")
for d in dups[:5]:
    print(f"  {d}")

# Check for broken HTML
broken = re.findall(r'>\s*data-i18n=', content)
print(f"Broken data-i18n (outside tag): {len(broken)}")

i18n_count = content.count('data-i18n=')
print(f"\ndata-i18n attributes: {i18n_count}")
print(f"File lines: {content.count(chr(10))+1}")
