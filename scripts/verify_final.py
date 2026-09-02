import sys,io,re
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace')
with open('dashboard/templates/landing.html','r',encoding='utf-8') as f:
    content=f.read()
checks=[
    ('pros_title','pros_title'),
    ('pros_instant','pros_instant'),
    ('pros_arabic','pros_arabic'),
    ('why_vex_pros_title','why_vex_pros_title'),
    ('vex_meta_info','vex_meta_info'),
    ('vex_desc','vex_desc'),
    ('vex_services_val','vex_services_val'),
    ('vex_support_val','vex_support_val'),
    ('vex_security_val','vex_security_val'),
    ('comp_desc_1xbet','comp_desc_1xbet'),
    ('comp_desc_melbet','comp_desc_melbet'),
    ('comp_desc_default','comp_desc_default'),
]
print('data-i18n attributes in HTML:')
for name, attr in checks:
    found=f'data-i18n="{attr}"' in content
    print(f'  {"OK" if found else "MISSING"}: {name}')
count=len(re.findall(r'data-i18n=',content))
print(f'Total data-i18n attributes: {count}')
