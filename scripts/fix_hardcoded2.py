import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

path = r'C:\Users\gnz\Downloads\boterx-dev\dashboard\templates\landing.html'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# ===== FIX 1: Replace hardcoded pros/cons section =====
old_pros = '''        <div class="pros-cons">
          <div><strong>\u062a\u0645 \u0627\u0644\u0645\u0645\u064a\u0632\u0627\u062a</strong><ul><li>\u062f\u0641\u0639 \u0641\u0648\u0631\u064a</li><li>\u062f\u0639\u0645 \u0639\u0631\u0628\u064a</li></ul></div>
          <div><strong>\u2b50 \u0644\u0645\u0627\u0630\u0627 VEX\u061f</strong><ul><li>\u0628\u0648\u0646\u0635 \u062d\u0635\u0631\u064a</li><li>\u0634\u0631\u064a\u0643 \u0645\u0639\u062a\u0645\u062f</li></ul></div>
        </div>'''
new_pros = '''        <div class="pros-cons">
          <div><strong data-i18n="pros_title">\u0627\u0644\u0645\u0645\u064a\u0632\u0627\u062a</strong><ul><li data-i18n="pros_instant">\u062f\u0641\u0639 \u0641\u0648\u0631\u064a</li><li data-i18n="pros_arabic">\u062f\u0639\u0645 \u0639\u0631\u0628\u064a</li><li data-i18n="pros_licensed">\u0645\u0631\u062e\u0635 \u0631\u0633\u0645\u064a\u0627\u064b</li></ul></div>
          <div><strong data-i18n="why_vex_pros_title">\u2b50 \u0644\u0645\u0627\u0630\u0627 VEX\u061f</strong><ul><li data-i18n="why_vex_bonus">\u0628\u0648\u0646\u0635 \u062d\u0635\u0631\u064a</li><li data-i18n="why_vex_verified">\u0634\u0631\u064a\u0643 \u0645\u0639\u062a\u0645\u062f</li><li data-i18n="why_vex_wallet">\u0645\u062d\u0641\u0638\u0629 \u0622\u0645\u0646\u0629</li></ul></div>
        </div>'''
if old_pros in content:
    content = content.replace(old_pros, new_pros)
    print("FIXED: pros/cons section")
else:
    print("SKIP: pros/cons already fixed or not found")

# ===== FIX 2: VEX card meta =====
old_vex_meta = '        <div class="comp-meta">Curacao 8048/JAZ \u2022 Cyprus \u2022 \u0645\u0646\u0630 2024 \u2022 4.9/5 \u2605 \u2022 5000+ \u0644\u0627\u0639\u0628</div>'
new_vex_meta = '        <div class="comp-meta"><span data-i18n="vex_meta_info">Curacao 8048/JAZ \u2022 Cyprus \u2022 \u0645\u0646\u0630 2024 \u2022 4.9/5 \u2605 \u2022 5000+ \u0644\u0627\u0639\u0628</span></div>'
if old_vex_meta in content:
    content = content.replace(old_vex_meta, new_vex_meta)
    print("FIXED: VEX meta")
else:
    print("SKIP: VEX meta")

# ===== FIX 3: VEX description paragraph =====
old_vex_desc = '''        VEX Games \u0645\u0646\u0635\u0629 \u0623\u0644\u0639\u0627\u0628 \u0645\u0627\u0644\u064a\u0629 \u0645\u0631\u062e\u0635\u0629 \u062a\u0639\u0645\u0644 \u0639\u0628\u0631 \u062a\u064a\u0644\u064a\u063a\u0631\u0627\u0645 \u0648\u0627\u0644\u0648\u064a\u0628 \u0628\u0640 17 \u0644\u063a\u0629. \u0646\u0648\u0641\u0631 \u0645\u062d\u0641\u0638\u0629 \u0645\u062a\u0643\u0627\u0645\u0644\u0629 (\u0625\u064a\u062f\u0627\u0639/\u0633\u062d\u0628 \u0641\u0648\u0631\u064a), \u0646\u0638\u0627\u0645 \u062a\u0639\u0648\u064a\u0636 \u0630\u0643\u064a SVRP (100% \u0631\u0635\u064a\u062f \u0645\u062c\u0645\u062f \u064a\u064f\u0641\u0643 \u0639\u0628\u0631 \u0627\u0644\u0623\u0635\u062f\u0642\u0627\u0621), Provably Fair \u0628\u0640 HMAC-SHA256, \u0648\u0634\u0631\u0627\u0643\u0629 \u0645\u0628\u0627\u0634\u0631\u0629 \u0645\u0639 1xPartners \u0648 MelPartners \u2014 \u0643\u0644 \u062a\u0633\u062c\u064a\u0644 \u0639\u0628\u0631\u0646\u0627 \u0645\u062d\u0633\u0648\u0628 \u0644\u0643, \u0648\u0643\u0644 \u0625\u064a\u062f\u0627\u0639 \u0645\u062d\u0645\u064a. '''
new_vex_desc = '<span data-i18n="vex_desc">VEX Games \u0645\u0646\u0635\u0629 \u0623\u0644\u0639\u0627\u0628 \u0645\u0627\u0644\u064a\u0629 \u0645\u0631\u062e\u0635\u0629 \u062a\u0639\u0645\u0644 \u0639\u0628\u0631 \u062a\u064a\u0644\u064a\u063a\u0631\u0627\u0645 \u0648\u0627\u0644\u0648\u064a\u0628 \u0628\u0640 17 \u0644\u063a\u0629. \u0646\u0648\u0641\u0631 \u0645\u062d\u0641\u0638\u0629 \u0645\u062a\u0643\u0627\u0645\u0644\u0629 (\u0625\u064a\u062f\u0627\u0639/\u0633\u062d\u0628 \u0641\u0648\u0631\u064a), \u0646\u0638\u0627\u0645 \u062a\u0639\u0648\u064a\u0636 \u0630\u0643\u064a SVRP (100% \u0631\u0635\u064a\u062f \u0645\u062c\u0645\u062f \u064a\u064f\u0641\u0643 \u0639\u0628\u0631 \u0627\u0644\u0623\u0635\u062f\u0642\u0627\u0621), Provably Fair \u0628\u0640 HMAC-SHA256, \u0648\u0634\u0631\u0627\u0643\u0629 \u0645\u0628\u0627\u0634\u0631\u0629 \u0645\u0639 1xPartners \u0648 MelPartners \u2014 \u0643\u0644 \u062a\u0633\u062c\u064a\u0644 \u0639\u0628\u0631\u0646\u0627 \u0645\u062d\u0633\u0648\u0628 \u0644\u0643, \u0648\u0643\u0644 \u0625\u064a\u062f\u0627\u0639 \u0645\u062d\u0645\u064a.</span>'''
if old_vex_desc in content:
    content = content.replace(old_vex_desc, new_vex_desc)
    print("FIXED: VEX description")
else:
    print("SKIP: VEX desc")

# ===== FIX 4: VEX table values =====
# Services value
old_svc = '<td data-i18n="vex_services">\u0627\u0644\u062e\u062f\u0645\u0627\u062a</td><td>8 \u0623\u0644\u0639\u0627\u0628'
new_svc = '<td data-i18n="vex_services">\u0627\u0644\u062e\u062f\u0645\u0627\u062a</td><td data-i18n="vex_services_val">8 \u0623\u0644\u0639\u0627\u0628'
if old_svc in content:
    content = content.replace(old_svc, new_svc, 1)
    print("FIXED: VEX services val")

old_sup = '<td data-i18n="vex_support">\u0627\u0644\u062f\u0639\u0645</td><td>24/7 \u0639\u0631\u0628\u064a'
new_sup = '<td data-i18n="vex_support">\u0627\u0644\u062f\u0639\u0645</td><td data-i18n="vex_support_val">24/7 \u0639\u0631\u0628\u064a'
if old_sup in content:
    content = content.replace(old_sup, new_sup, 1)
    print("FIXED: VEX support val")

old_sec = '<td data-i18n="vex_security">\u0627\u0644\u0623\u0645\u0627\u0646</td><td>\u062a\u0634\u0641\u064a\u0631 \u0643\u0627\u0645\u0644'
new_sec = '<td data-i18n="vex_security">\u0627\u0644\u0623\u0645\u0627\u0646</td><td data-i18n="vex_security_val">\u062a\u0634\u0641\u064a\u0631 \u0643\u0627\u0645\u0644'
if old_sec in content:
    content = content.replace(old_sec, new_sec, 1)
    print("FIXED: VEX security val")

# ===== FIX 5: Company descriptions - wrap in data-i18n =====
# Replace hardcoded Jinja descriptions with JS-translatable versions
old_1xbet = "{% if c.name == '1XBET' %}1xBet \u0639\u0645\u064a\u0644\u0627\u0642 \u0627\u0644\u0645\u0631\u0627\u0647\u0646\u0627\u062a \u0627\u0644\u0639\u0627\u0644\u0645\u064a \u0628\u062a\u0631\u062e\u064a\u0635 \u0643\u0648\u0631\u0627\u0633\u0627\u0648 \u2014 1000+ \u0633\u0648\u0642 \u064a\u0648\u0645\u064a\u0627\u064b\u060c \u0628\u062b \u0645\u0628\u0627\u0634\u0631\u060c \u0643\u0627\u0632\u064a\u0646\u0648 \u0636\u062e\u0645 \u0648\u0633\u062d\u0628 \u0641\u0648\u0631\u064a. \u0645\u0639 VEX \u062a\u062d\u0635\u0644 \u0639\u0644\u0649 \u062a\u0633\u062c\u064a\u0644 \u0645\u0628\u0627\u0634\u0631 \u0648\u0643\u0648\u062f <b>{{ c.promo_code or 'VEX' }}</b> \u0648\u0628\u0648\u0646\u0635 \u062a\u0631\u062d\u064a\u0628\u064a \u062d\u062a\u0649 130%.{% elif"
new_1xbet = "{% if c.name == '1XBET' %}<span data-i18n=\"comp_desc_1xbet\">1xBet \u0639\u0645\u064a\u0644\u0627\u0642 \u0627\u0644\u0645\u0631\u0627\u0647\u0646\u0627\u062a \u0627\u0644\u0639\u0627\u0644\u0645\u064a \u0628\u062a\u0631\u062e\u064a\u0635 \u0643\u0648\u0631\u0627\u0633\u0627\u0648 \u2014 1000+ \u0633\u0648\u0642 \u064a\u0648\u0645\u064a\u0627\u064b\u060c \u0628\u062b \u0645\u0628\u0627\u0634\u0631\u060c \u0643\u0627\u0632\u064a\u0646\u0648 \u0636\u062e\u0645 \u0648\u0633\u062d\u0628 \u0641\u0648\u0631\u064a. \u0645\u0639 VEX \u062a\u062d\u0635\u0644 \u0639\u0644\u0649 \u062a\u0633\u062c\u064a\u0644 \u0645\u0628\u0627\u0634\u0631 \u0648\u0643\u0648\u062f <b>{{ c.promo_code or 'VEX' }}</b> \u0648\u0628\u0648\u0646\u0635 \u062a\u0631\u062d\u064a\u0628\u064a \u062d\u062a\u0649 130%.</span>{% elif"
if old_1xbet in content:
    content = content.replace(old_1xbet, new_1xbet)
    print("FIXED: 1XBET desc")

old_melbet = "{% elif c.name == 'MELBET' %}Melbet \u0645\u0631\u062e\u0635\u0629 \u0648\u0645\u0648\u062b\u0648\u0642\u0629 \u2014 \u0648\u0627\u062c\u0647\u0629 \u0639\u0631\u0628\u064a\u0629 \u0645\u0645\u062a\u0627\u0632\u0629\u060c \u0627\u062d\u062a\u0645\u0627\u0644\u0627\u062a \u0639\u0627\u0644\u064a\u0629\u060c \u062f\u0641\u0639 \u0641\u0648\u0631\u064a \u0639\u0628\u0631 \u0641\u0648\u062f\u0627\u0641\u0648\u0646 \u0643\u0627\u0634 \u0648STC Pay. \u0633\u062c\u0651\u0644 \u0639\u0628\u0631 VEX \u0628\u0643\u0648\u062f {{ c.promo_code or 'VEX' }}.{% else %}"
new_melbet = "{% elif c.name == 'MELBET' %}<span data-i18n=\"comp_desc_melbet\">Melbet \u0645\u0631\u062e\u0635\u0629 \u0648\u0645\u0648\u062b\u0648\u0642\u0629 \u2014 \u0648\u0627\u062c\u0647\u0629 \u0639\u0631\u0628\u064a\u0629 \u0645\u0645\u062a\u0627\u0632\u0629\u060c \u0627\u062d\u062a\u0645\u0627\u0644\u0627\u062a \u0639\u0627\u0644\u064a\u0629\u060c \u062f\u0641\u0639 \u0641\u0648\u0631\u064a \u0639\u0628\u0631 \u0641\u0648\u062f\u0627\u0641\u0648\u0646 \u0643\u0627\u0634 \u0648STC Pay. \u0633\u062c\u0651\u0644 \u0639\u0628\u0631 VEX \u0628\u0643\u0648\u062f {{ c.promo_code or 'VEX' }}.</span>{% else %}"
if old_melbet in content:
    content = content.replace(old_melbet, new_melbet)
    print("FIXED: MELBET desc")

old_default = "{% else %}{{ c.name }} \u0634\u0631\u0643\u0629 \u0645\u0631\u0627\u0647\u0646\u0627\u062a \u0645\u0631\u062e\u0635\u0629 {{ c.license }} \u2014 \u0645\u0642\u0631\u0647\u0627 {{ c.headquarters }}\u060c \u062a\u0623\u0633\u0633\u062a {{ c.founded }}\u060c \u062a\u0642\u064a\u064a\u0645 {{ c.rating }}/5. \u062a\u0642\u062f\u0645 \u0628\u0648\u0646\u0635 \u062a\u0631\u062d\u064a\u0628\u064a\u060c \u062f\u0641\u0639 \u0641\u0648\u0631\u064a \u0648\u062f\u0639\u0645 \u0639\u0631\u0628\u064a. \u0633\u062c\u0651\u0644 \u0639\u0628\u0631 VEX \u0627\u0644\u0622\u0646.{% endif %}"
new_default = "{% else %}<span data-i18n=\"comp_desc_default\">{{ c.name }} \u0634\u0631\u0643\u0629 \u0645\u0631\u0627\u0647\u0646\u0627\u062a \u0645\u0631\u062e\u0635\u0629 {{ c.license }} \u2014 \u0645\u0642\u0631\u0647\u0627 {{ c.headquarters }}\u060c \u062a\u0623\u0633\u0633\u062a {{ c.founded }}\u060c \u062a\u0642\u064a\u064a\u0645 {{ c.rating }}/5. \u062a\u0642\u062f\u0645 \u0628\u0648\u0646\u0635 \u062a\u0631\u062d\u064a\u0628\u064a\u060c \u062f\u0641\u0639 \u0641\u0648\u0631\u064a \u0648\u062f\u0639\u0645 \u0639\u0631\u0628\u064a. \u0633\u062c\u0651\u0644 \u0639\u0628\u0631 VEX \u0627\u0644\u0622\u0646.</span>{% endif %}"
if old_default in content:
    content = content.replace(old_default, new_default)
    print("FIXED: default desc")

# ===== FIX 6: Aria labels =====
aria_fixes = [
    ('\u0627\u062e\u062a\u0631 \u0627\u0644\u0644\u063a\u0629', 'Select language'),
    ('\u0627\u0644\u0628\u062d\u062b \u0639\u0646 \u0644\u063a\u0629', 'Search language'),
    ('\u0627\u0644\u0642\u0627\u0626\u0645\u0629', 'Menu'),
    ('\u0625\u063a\u0644\u0627\u0642 \u0627\u0644\u0642\u0627\u0626\u0645\u0629', 'Close menu'),
    ('\u0642\u0627\u0626\u0645\u0629 \u0627\u0644\u062c\u0648\u0627\u0644', 'Mobile menu'),
]
for ar, en in aria_fixes:
    if ar in content:
        content = content.replace(ar, en)

# Fix search placeholder  
content = content.replace('placeholder="\u0627\u0644\u0628\u062d\u062b \u0639\u0646 \u0644\u063a\u0629..."', 'placeholder="Search language..."')

# Fix copy button title
content = content.replace('title="\u0646\u0633\u062e \u0627\u0644\u0643\u0648\u062f"', 'title="Copy code"')

print("FIXED: aria-labels, placeholders, titles")

# Write back
with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"\nDone! File size: {len(content)} chars")
