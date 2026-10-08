import sys,io,re
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace')
with open('dashboard/templates/landing.html','r',encoding='utf-8') as f:
    content=f.read()

# Find all elements with data-i18n
pattern=r'data-i18n="([^"]+)"'
matches=re.findall(pattern,content)
print(f'Total data-i18n elements: {len(matches)}')
print(f'Unique keys: {len(set(matches))}')

# Check which keys have translation values in en block
en_start=content.find('  en: {')
en_end=content.find('\n  fr: {')
en_block=content[en_start:en_end]

# Check each key
missing_in_en=[]
for key in set(matches):
    if key+':' not in en_block:
        missing_in_en.append(key)
if missing_in_en:
    print(f'\nKeys in HTML but NOT in en translations: {missing_in_en}')
else:
    print('\nAll data-i18n keys have English translations')

# Check for duplicate placeholder
if content.count('placeholder="Search language..."') > 1:
    print('\nWARNING: Duplicate placeholder attribute found')

# Check if lang-trigger text shows English by default
idx=content.find('id="currentLang"')
print(f'\ncurrentLang default text: {content[idx:idx+50]}')
