import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

path = r'C:\Users\gnz\Downloads\boterx-dev\dashboard\templates\landing.html'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Track changes
changed = 0

# Line 1489 (index 1488): 1XBET description
old = lines[1488]
new = old.replace(
    "1xBet عملاق المراهنات العالمي بترخيص كوراساو",
    "<span data-i18n=\"comp_desc_1xbet\">1xBet عملاق المراهنات العالمي بترخيص كوراساو"
)
if new != old:
    lines[1488] = new
    changed += 1
    print("FIXED: 1XBET desc opening tag")

# Line 1490 (index 1489): MELBET description  
old = lines[1489]
new = old.replace(
    "Melbet مرخصة وموثوقة",
    "<span data-i18n=\"comp_desc_melbet\">Melbet مرخصة وموثوقة"
)
if new != old:
    lines[1489] = new
    changed += 1
    print("FIXED: MELBET desc opening tag")

# Line 1491 (index 1490): Default description
old = lines[1490]
new = old.replace(
    "{% else %}{{ c.name }} شركة مراهنة مرخصة",
    "{% else %}<span data-i18n=\"comp_desc_default\">{{ c.name }} شركة مراهنة مرخصة"
)
if new != old:
    lines[1490] = new
    changed += 1
    print("FIXED: default desc opening tag")

# Line 1491 (index 1490) end: close span before {% endif %}
old = lines[1490]
if 'comp_desc_default' in old and '</span>' not in old:
    new = old.replace('{% endif %}', '</span>{% endif %}')
    lines[1490] = new
    changed += 1
    print("FIXED: default desc closing tag")

# Line 1489 end: close span for 1XBET before {% elif %}
old = lines[1488]
if 'comp_desc_1xbet' in old and '</span>' not in old:
    new = old.replace('{% elif', '</span>{% elif')
    lines[1488] = new
    changed += 1
    print("FIXED: 1XBET desc closing tag")

# Line 1490: close span for MELBET before {% else %}
old = lines[1489]
if 'comp_desc_melbet' in old and '</span>' not in old:
    new = old.replace('{% else %}', '</span>{% else %}')
    lines[1489] = new
    changed += 1
    print("FIXED: MELBET desc closing tag")

# VEX description line 1532 (index 1531)
old = lines[1531]
new = old.replace(
    '        VEX Games منصة ألعاب مالية مرخصة',
    '        <span data-i18n="vex_desc">VEX Games منصة ألعاب مالية مرخصة'
)
if new != old:
    lines[1531] = new
    changed += 1
    print("FIXED: VEX desc opening tag")

old = lines[1531]
if 'vex_desc' in old and '</span>' not in old:
    # Add </span> before the newline
    new = old.rstrip('\n').rstrip() + '</span>\n' if old.endswith('\n') else old.rstrip() + '</span>\n'
    lines[1531] = new
    changed += 1
    print("FIXED: VEX desc closing tag")

# Write back
with open(path, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print(f"\nTotal line changes: {changed}")
print(f"File: {sum(len(l) for l in lines)} chars")
