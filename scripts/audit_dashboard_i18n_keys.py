#!/usr/bin/env python3
import glob
import os
import re


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_JS = os.path.join(ROOT, 'dashboard', 'static', 'js', 'app.js')
TPL_GLOB = os.path.join(ROOT, 'dashboard', 'templates', '*.html')


def parse_dict_keys(section_text):
    keys = []
    for m in re.finditer(r'([A-Za-z_][A-Za-z0-9_]*)\s*:', section_text):
        keys.append(m.group(1))
    return keys


def main():
    app = open(APP_JS, 'r', encoding='utf-8').read()

    mar = re.search(r'ar\s*:\s*\{([\s\S]*?)\n\s*\},\s*en\s*:\s*\{', app)
    men = re.search(r'en\s*:\s*\{([\s\S]*?)\n\s*\}\s*;', app)
    if not mar or not men:
        print('Could not parse app.js dictionaries')
        return

    ar_keys_all = parse_dict_keys(mar.group(1))
    en_keys_all = parse_dict_keys(men.group(1))
    ar_keys = set(ar_keys_all)
    en_keys = set(en_keys_all)

    used = set()
    used_by_file = {}
    key_pat = re.compile(r'data-i18n(?:-placeholder|-title)?\s*=\s*"([^"]+)"')
    tr_pat = re.compile(r"\b(?:tr|t)\(\s*'([^']+)'\s*\)")
    for fp in glob.glob(TPL_GLOB):
        s = open(fp, 'r', encoding='utf-8').read()
        keys = set(key_pat.findall(s))
        keys.update(tr_pat.findall(s))
        if keys:
            used_by_file[os.path.basename(fp)] = keys
            used.update(keys)

    missing_both = sorted([k for k in used if k not in ar_keys and k not in en_keys])
    only_ar = sorted([k for k in used if k in ar_keys and k not in en_keys])
    only_en = sorted([k for k in used if k in en_keys and k not in ar_keys])

    print(f'AR keys total={len(ar_keys_all)} unique={len(ar_keys)}')
    print(f'EN keys total={len(en_keys_all)} unique={len(en_keys)}')
    print(f'AR duplicate keys={len(ar_keys_all)-len(ar_keys)}')
    print(f'Used keys in templates={len(used)}')
    print(f'Missing in both={len(missing_both)}')
    print(f'Used keys only in AR={len(only_ar)}')
    print(f'Used keys only in EN={len(only_en)}')

    if missing_both:
        print('\nMissing keys (both):')
        for k in missing_both:
            print(' -', k)

    print('\nFiles with most missing keys:')
    items = []
    for fn, ks in used_by_file.items():
        cnt = sum(1 for k in ks if k not in ar_keys and k not in en_keys)
        if cnt:
            items.append((cnt, fn))
    for cnt, fn in sorted(items, reverse=True)[:20]:
        print(f' - {fn}: {cnt}')


if __name__ == '__main__':
    main()
