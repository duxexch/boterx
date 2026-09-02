import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

path = r'C:\Users\gnz\Downloads\boterx-dev\dashboard\templates\landing.html'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Check for each hardcoded string
checks = [
    ('pros_hardcoded', 'المميزات'),
    ('pros_instant', 'دفع فوري'),
    ('pros_arabic', 'دعم عربي'),
    ('why_vex', 'لماذا VEX'),
    ('bonus', 'بونص حصري'),
    ('verified', 'شريك معتمد'),
    ('vex_meta', '5000+ لاعب'),
    ('vex_desc', 'نوفر محفظة متكاملة'),
    ('vex_games_list', '8 ألعاب'),
    ('vex_support_val', 'عربي/إنجليزي'),
    ('vex_security_val', 'تشفير كامل'),
    ('copy_btn_title', 'نسخ الكود'),
    ('search_placeholder', 'البحث عن لغة'),
    ('aria_lang', 'اختر اللغة'),
    ('aria_menu', 'القائمة'),
    ('aria_close', 'إغلاق القائمة'),
    ('aria_mobile', 'قائمة الجوال'),
    ('company_desc_1xbet', 'عملاق المراهنات'),
    ('company_desc_melbet', 'Melbet مرخصة'),
]
for name, text in checks:
    found = text in content
    print(f'  {"FOUND" if found else "MISSING"}: {name} ({text[:30]})')
