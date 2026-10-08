import re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

path = r'C:\Users\gnz\Downloads\boterx-dev\dashboard\templates\landing.html'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Extract all data-i18n keys used in HTML
html_keys = set(re.findall(r'data-i18n="([^"]+)"', content))
print(f"Keys used in HTML: {len(html_keys)}")
print(sorted(html_keys))

# Extract keys per language from I18N_TRANSLATIONS
for lang in ['ar', 'en', 'fr', 'es']:
    pattern = rf'{lang}:\s*\{{'
    match = re.search(pattern, content)
    if match:
        start = match.start()
        # Find matching closing brace
        depth = 0
        idx = start + len(match.group()) - 1
        while idx < len(content):
            if content[idx] == '{': depth += 1
            elif content[idx] == '}':
                depth -= 1
                if depth == 0:
                    block = content[start:idx+1]
                    lang_keys = set(re.findall(r'(\w+):', block))
                    # Remove non-key matches
                    lang_keys = {k for k in lang_keys if k != lang}
                    missing = html_keys - lang_keys
                    extra = lang_keys - html_keys
                    print(f"\n{lang}: {len(lang_keys)} keys")
                    if missing:
                        print(f"  MISSING from HTML: {sorted(missing)}")
                    break
            idx += 1
