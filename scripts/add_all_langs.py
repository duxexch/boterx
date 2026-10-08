import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

path = r'C:\Users\gnz\Downloads\boterx-dev\dashboard\templates\landing.html'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# The es block ends with this exact line, then };
old_end = '    footer_responsible: "18+ \\u2014 Juega Responsablemente"\n  }\n};;'
new_end = '    footer_responsible: "18+ \\u2014 Juega Responsablemente"\n  }\n};'

if old_end not in content:
    print("ERROR: Could not find es block ending pattern")
    sys.exit(1)

# Read the new languages file
with open(r'C:\Users\gnz\Downloads\boterx-dev\scripts\new_langs.txt', 'r', encoding='utf-8') as f:
    new_langs = f.read()

content = content.replace(old_end, new_end + '\n' + new_langs + '\n};')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

# Verify
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Count language blocks
langs_found = []
for lang in ['ar', 'en', 'fr', 'es', 'de', 'it', 'pt', 'ru', 'zh', 'tr', 'ur', 'hi', 'fa', 'id', 'ja', 'ko', 'th']:
    if lang + ': {' in content:
        langs_found.append(lang)

print(f"Languages found: {len(langs_found)} - {', '.join(langs_found)}")
print(f"File size: {len(content)} chars, {content.count(chr(10))+1} lines")
