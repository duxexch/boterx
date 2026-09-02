import re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

path = r'C:\Users\gnz\Downloads\boterx-dev\dashboard\templates\landing.html'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

orig = len(content)

# === 1. Fix data-i18n wiring for existing keys ===
# Navbar
content = content.replace('<span class="btn-text">ألعابي</span>', '<span class="btn-text" data-i18n="nav_games">ألعابي</span>')
content = content.replace('<span class="btn-text">دخول</span>', '<span class="btn-text" data-i18n="nav_login">دخول</span>')
content = content.replace('>الشركات<', ' data-i18n="nav_companies">الشركات<')
content = content.replace('>ألعابي<', ' data-i18n="nav_games">ألعابي<')
content = content.replace('>دخول<', ' data-i18n="nav_login">دخول<')
content = content.replace('اللغة</label>', '<span data-i18n="mobile_lang_label">اللغة</span></label>')
content = content.replace('<span class="mobile-menu-title">القائمة</span>', '<span class="mobile-menu-title" data-i18n="mobile_menu_title">القائمة</span>')

# Company card fields
content = content.replace('>الترخيص</td><td>', ' data-i18n="comp_license">الترخيص</td><td>')
content = content.replace('>المقر</td><td>', ' data-i18n="comp_headquarters">المقر</td><td>')
content = content.replace('>التأسيس</td><td>', ' data-i18n="comp_founded">التأسيس</td><td>')
content = content.replace('>كود البرومو</td><td>', ' data-i18n="comp_promo">كود البرومو</td><td>')

# Company CTA
content = content.replace('>سجّل في {{ c.name }}</a>', ' data-i18n="comp_cta_register">سجّل في {{ c.name }}</a>')
content = content.replace('>تحميل التطبيق</a>', ' data-i18n="download_app">تحميل التطبيق</a>')
content = content.replace('>تفاصيل</a>', ' data-i18n="comp_cta_details">تفاصيل</a>')
content = content.replace('>موثوق</span>', ' data-i18n="badge_trusted">موثوق</span>')

# Pros/Cons
content = content.replace('>المميزات</strong>', ' data-i18n="features_title">المميزات</strong>')
content = content.replace('>لماذا VEX؟</strong>', ' data-i18n="why_vex_title">لماذا VEX؟</strong>')

# VEX section
content = content.replace('>شريك معتمد</span>', ' data-i18n="vex_badge">شريك معتمد</span>')
content = content.replace('>الترخيص</td><td>VEX', ' data-i18n="vex_license">الترخيص</td><td>VEX')
content = content.replace('>الخدمات</td><td>', ' data-i18n="vex_services">الخدمات</td><td>')
content = content.replace('>الدعم</td><td>', ' data-i18n="vex_support">الدعم</td><td>')
content = content.replace('>الأمان</td><td>', ' data-i18n="vex_security">الأمان</td><td>')

# Step descriptions
content = content.replace('>قارن التراخيص والتقييمات أعلاه</div>', ' data-i18n="step1_desc">قارن التراخيص والتقييمات أعلاه</div>')
content = content.replace("اضغط <b>سجّل</b> → رابط إحالتك الخاص يفتح</div>", " data-i18n=\"step2_desc\">اضغط <b>سجّل</b> → رابط إحالتك الخاص يفتح</div>")
content = content.replace('>محفظة VEX + تعويض 100% + Provably Fair</div>', ' data-i18n="step3_desc">محفظة VEX + تعويض 100% + Provably Fair</div>')

# FAQ answers
content = content.replace('نعم — كل الشركات المعروضة مرخصة كوراساو 8048/JAZ أو ما يعادلها، ومقراتها في قبرص/مالطا. VEX تعرض فقط المرخص.</div>', ' data-i18n="faq_a1">نعم — كل الشركات المعروضة مرخصة كوراساو 8048/JAZ أو ما يعادلها، ومقراتها في قبرص/مالطا. VEX تعرض فقط المرخص.</div>')
content = content.replace('كود خاص من VEX يعطيك بونص إضافي عند التسجيل (مثال 1XBET: <code>VEX</code>). استخدمه في حقل البرومو عند التسجيل.</div>', ' data-i18n="faq_a2">كود خاص من VEX يعطيك بونص إضافي عند التسجيل (مثال 1XBET: <code>VEX</code>). استخدمه في حقل البرومو عند التسجيل.</div>')
content = content.replace('نعم — VEX شريك مباشر مع 1xPartners و MelPartners و6 شبكات أخرى. كل تسجيل عبر <code>vex.deals/go/*</code> محسوب لك.</div>', ' data-i18n="faq_a3">نعم — VEX شريك مباشر مع 1xPartners و MelPartners و6 شبكات أخرى. كل تسجيل عبر <code>vex.deals/go/*</code> محسوب لك.</div>')
content = content.replace('محفظة VEX منفصلة — تودع عبر فودافون كاش/STC Pay/بنكي، تلعب، تسحب بنفس الوسيلة بإشراف 24/7. التعويض عبر SVRP يضمن 100%.</div>', ' data-i18n="faq_a4">محفظة VEX منفصلة — تودع عبر فودافون كاش/STC Pay/بنكي، تلعب، تسحب بنفس الوسيلة بإشراف 24/7. التعويض عبر SVRP يضمن 100%.</div>')

# Footer
content = content.replace('© 2026 VEX Games — شريك معتمد • 8 شركات مرخصة • 17 لغة • Provably Fair', '<span data-i18n="footer_copyright">© 2026 VEX Games — شريك معتمد • 8 شركات مرخصة • 17 لغة • Provably Fair</span>')
content = content.replace('18+ — العب بمسؤولية', '<span data-i18n="footer_responsible">18+ — العب بمسؤولية</span>')

# Copy button
content = content.replace('>نسخ الكود</button>', ' data-i18n="copy_code_btn">نسخ الكود</button>')
content = content.replace("onclick=\"copyPromo(", "onclick=\"copyPromo(")

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Count data-i18n attributes
i18n_count = content.count('data-i18n=')
print(f"File: {len(content)} chars, {content.count(chr(10))+1} lines")
print(f"data-i18n attributes: {i18n_count}")
