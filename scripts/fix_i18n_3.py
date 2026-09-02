import re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

path = r'C:\Users\gnz\Downloads\boterx-dev\dashboard\templates\company_detail.html'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

orig_lines = content.count('\n') + 1

# 1. Fix HTML lang/dir
content = content.replace('<html lang="ar" dir="rtl">', '<html lang="ar" dir="rtl" id="htmlRoot">')

# 2. Add data-i18n attributes to all Arabic text in the body
# Topbar
content = content.replace('>العودة للرئيسية</a>', ' data-i18n="back_to_home">العودة للرئيسية</a>')

# Badge
content = content.replace('>شريك معتمد VEX</span>', ' data-i18n="detail_badge">شريك معتمد VEX</span>')

# Meta
content = content.replace('>تأسست {{ company.founded }}</span>', ' data-i18n="detail_founded">تأسست {{ company.founded }}</span>')
content = content.replace('{{ company.rating }}/5 نجوم</span>', '{{ company.rating }}/5 <span data-i18n="detail_stars">نجوم</span></span>')

# Section headings
content = content.replace('>كود البرومو الحصري</h2>', ' data-i18n="detail_promo_title">كود البرومو الحصري</h2>')
content = content.replace('>استخدم هذا الكود عند التسجيل</div>', ' data-i18n="detail_promo_hint">استخدم هذا الكود عند التسجيل</div>')
content = content.replace('>سجّل في {{ company.name }} الآن</a>', ' data-i18n="detail_cta_register">سجّل في {{ company.name }} الآن</a>')
content = content.replace('>تحميل التطبيق</a>', ' data-i18n="detail_cta_app">تحميل التطبيق</a>')
content = content.replace('>نظرة عامة</h2>', ' data-i18n="detail_overview">نظرة عامة</h2>')
content = content.replace('>تفاصيل الشركة</h2>', ' data-i18n="detail_table_title">تفاصيل الشركة</h2>')
content = content.replace('>المميزات والعيوب</h2>', ' data-i18n="detail_pros_cons">المميزات والعيوب</h2>')
content = content.replace('>المميزات</h3>', ' data-i18n="detail_pros">المميزات</h3>')
content = content.replace('>العيوب</h3>', ' data-i18n="detail_cons">العيوب</h3>')
content = content.replace('>لماذا تسجل عبر VEX؟</h2>', ' data-i18n="detail_why_title">لماذا تسجل عبر VEX؟</h2>')
content = content.replace('>شركات مشابهة</h2>', ' data-i18n="detail_similar">شركات مشابهة</h2>')

# Table rows
content = content.replace('>الاسم</td><td>', ' data-i18n="detail_label_name">الاسم</td><td>')
content = content.replace('>الترخيص</td><td>', ' data-i18n="detail_label_license">الترخيص</td><td>')
content = content.replace('>المقر</td><td>', ' data-i18n="detail_label_hq">المقر</td><td>')
content = content.replace('>التأسيس</td><td>', ' data-i18n="detail_label_founded">التأسيس</td><td>')
content = content.replace('>التقييم</td><td>', ' data-i18n="detail_label_rating">التقييم</td><td>')
content = content.replace('>كود البرومو</td><td>', ' data-i18n="detail_label_promo">كود البرومو</td><td>')

# Similar cards stars
content = content.replace('{{ s.rating }}/5 نجوم</div>', '{{ s.rating }}/5 <span data-i18n="detail_stars">نجوم</span></div>')

# Footer
content = content.replace('شريك معتمد<br>', '<span data-i18n="detail_footer_partner">شريك معتمد</span><br>')
content = content.replace('18+ - العب بمسؤولية</div>', '<span data-i18n="detail_footer_responsible">18+ - العب بمسؤولية</span></div>')

# Copy button
content = content.replace('>نسخ الكود</button>', ' data-i18n="detail_copy_btn">نسخ الكود</button>')

# VEX partnership paragraph
content = content.replace('VEX شريك معتمد مباشر مع {{ company.name }}. كل تسجيل عبر روابطنا محسوب لك بشكل مباشر. نوفر لك كود البرومو الحصري ورابط التسجيل المباشر WITHOUT أي عمولات إضافية عليك.', '<span data-i18n="detail_why_desc">VEX شريك معتمد مباشر مع {{ company.name }}. كل تسجيل عبر روابطنا محسوب لك بشكل مباشر. نوفر لك كود البرومو الحصري ورابط التسجيل المباشر WITHOUT أي عمولات إضافية عليك.</span>')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

i18n_count = content.count('data-i18n=')
print(f"File: {len(content)} chars, {content.count(chr(10))+1} lines")
print(f"data-i18n attributes: {i18n_count}")
