import sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

path = r'C:\Users\gnz\Downloads\boterx-dev\dashboard\templates\landing.html'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# === FIX 1: Company card pros/why-VEX (lines 1501-1504) ===
old_pros = '''        <div class="pros-cons">
          <div><strong>تم المميزات</strong><ul><li>دفع فوري</li><li>دعم عربي</li></ul></div>
          <div><strong>⭐ لماذا VEX؟</strong><ul><li>بونص حصري</li><li>شريك معتمد</li></ul></div>
        </div>'''
new_pros = '''        <div class="pros-cons">
          <div><strong data-i18n="pros_title">المميزات</strong><ul><li data-i18n="pros_instant">دفع فوري</li><li data-i18n="pros_arabic">دعم عربي</li><li data-i18n="pros_licensed">مرخص رسمياً</li></ul></div>
          <div><strong data-i18n="why_vex_pros_title">⭐ لماذا VEX؟</strong><ul><li data-i18n="why_vex_bonus">بونص حصري</li><li data-i18n="why_vex_verified">شريك معتمد</li><li data-i18n="why_vex_wallet">محفظة آمنة</li></ul></div>
        </div>'''
content = content.replace(old_pros, new_pros)

# === FIX 2: VEX card meta line ===
old_vex_meta = '        <div class="comp-meta">Curacao 8048/JAZ • Cyprus • منذ 2024 • 4.9/5 ★ • 5000+ لاعب</div>'
new_vex_meta = '        <div class="comp-meta"><span data-i18n="vex_meta_info">Curacao 8048/JAZ \u2022 Cyprus \u2022 Since 2024 \u2022 4.9/5 \u2605 \u2022 5000+ Players</span></div>'
content = content.replace(old_vex_meta, new_vex_meta)

# === FIX 3: VEX description paragraph ===
old_vex_desc = '''        VEX Games منصة ألعاب مالية مرخصة تعمل عبر تيليغرام والويب بـ 17 لغة. نوفر محفظة متكاملة (إيداع/سحب فوري)، نظام تعويض ذكي SVRP (100% رصيد مجمد يُفك عبر الأصدقاء)، Provably Fair بـ HMAC-SHA256، وشراكة مباشرة مع 1xPartners و MelPartners — كل تسجيل عبرنا محسوب لك، وكل إيداع محمي.'''
new_vex_desc = '<span data-i18n="vex_desc">VEX Games licensed financial gaming platform via Telegram and Web in 17 languages. Integrated wallet (instant deposit/withdrawal), smart SVRP compensation system (100% frozen balance unlocked via friends), Provably Fair with HMAC-SHA256, direct partnership with 1xPartners and MelPartners \u2014 every registration through us counts for you, every deposit is protected.</span>'
content = content.replace(old_vex_desc, new_vex_desc)

# === FIX 4: VEX table values ===
old_vex_svc = '<td data-i18n="vex_services">\u0627\u0644\u062e\u062f\u0645\u0627\u062a</td><td>8 \u0623\u0644\u0639\u0627\u0628 (\u0645\u0646\u0627\u062c\u0645/\u0643\u0631\u0627\u0634/\u0623\u0641\u064a\u0627\u062a\u0648\u0631/\u0628\u0644\u064a\u0646\u0643\u0648/\u0639\u062c\u0644\u0629/\u064a\u0627\u0646\u0635\u064a\u0628/\u0646\u0631\u062f/\u0633\u0646\u0627\u062a\u0634)</td>'
new_vex_svc = '<td data-i18n="vex_services">\u0627\u0644\u062e\u062f\u0645\u0627\u062a</td><td data-i18n="vex_services_val">8 \u0623\u0644\u0639\u0627\u0628 (\u0645\u0646\u0627\u062c\u0645/\u0643\u0631\u0627\u0634/\u0623\u0641\u064a\u0627\u062a\u0648\u0631/\u0628\u0644\u064a\u0646\u0643\u0648/\u0639\u062c\u0644\u0629/\u064a\u0627\u0646\u0635\u064a\u0628/\u0646\u0631\u062f/\u0633\u0646\u0627\u062a\u0634)</td>'
content = content.replace(old_vex_svc, new_vex_svc)

old_vex_sup = '<td data-i18n="vex_support">\u0627\u0644\u062f\u0639\u0645</td><td>24/7 \u0639\u0631\u0628\u064a/\u0625\u0646\u062c\u0644\u064a\u0632\u064a \u0639\u0628\u0631 @vex_wallet_bot</td>'
new_vex_sup = '<td data-i18n="vex_support">\u0627\u0644\u062f\u0639\u0645</td><td data-i18n="vex_support_val">24/7 Arabic/English via @vex_wallet_bot</td>'
content = content.replace(old_vex_sup, new_vex_sup)

old_vex_sec = '<td data-i18n="vex_security">\u0627\u0644\u0623\u0645\u0627\u0646</td><td>\u062a\u0634\u0641\u064a\u0631 \u0643\u0627\u0645\u0644 + \u062d\u0645\u0627\u064a\u0629 \u0645\u0646 \u0627\u0644\u062a\u0644\u0627\u0639\u0628 + \u0633\u062d\u0628/\u0625\u064a\u062f\u0627\u0639 \u0628\u0625\u0634\u0631\u0627\u0641</td>'
new_vex_sec = '<td data-i18n="vex_security">\u0627\u0644\u0623\u0645\u0627\u0646</td><td data-i18n="vex_security_val">Full encryption + anti-tampering + supervised deposit/withdrawal</td>'
content = content.replace(old_vex_sec, new_vex_sec)

# === FIX 5: Company descriptions - add data-i18n to comp-desc ===
# Replace the Jinja descriptions with data-i18n elements
old_desc = '''        <p class="comp-desc" itemprop="reviewBody">
          {% if c.name == '1XBET' %}1xBet عملاق المراهنات العالمي بترخيص كوراساو — 1000+ سوق يومياً، بث مباشر، كازينو ضخم وسحب فوري. مع VEX تحصل على تسجيل مباشر وكود <b>{{ c.promo_code or 'VEX' }}</b> وبونص ترحيبي حتى 130%.
          {% elif c.name == 'MELBET' %}Melbet مرخصة وموثوقة — واجهة عربية ممتازة، احتمالات عالية، دفع فوري عبر فودافون كاش وSTC Pay. سجّل عبر VEX بكود {{ c.promo_code or 'VEX' }}.
          {% else %}{{ c.name }} شركة مراهنة مرخصة {{ c.license }} — مقرها {{ c.headquarters }}، تأسست {{ c.founded }}، تقييم {{ c.rating }}/5. تقدم بونص ترحيبي، دفع فوري ودعم عربي. سجّل عبر VEX الآن.{% endif %}
        </p>'''
new_desc = '''        <p class="comp-desc" itemprop="reviewBody" data-i18n="comp_desc_{{ c.name|lower }}">
          {{ c.name }}
        </p>'''
content = content.replace(old_desc, new_desc)

# === FIX 6: Copy button title ===
content = content.replace('title="\u0646\u0633\u062e \u0627\u0644\u0643\u0648\u062f"', 'title="Copy"')
# Also fix the copy button icon text
content = content.replace(">cnsp</button>", ' data-i18n="copy_code_btn">Copy</button>')

# === FIX 7: Aria labels ===
content = content.replace('aria-label="\u0627\u062e\u062a\u0631 \u0627\u0644\u0644\u063a\u0629" title="\u0627\u062e\u062a\u0631 \u0627\u0644\u0644\u063a\u0629"', 'aria-label="Select language" title="Select language"')
content = content.replace('placeholder="\u0627\u0644\u0628\u062d\u062b \u0639\u0646 \u0644\u063a\u0629..."', 'placeholder="Search language..."')
content = content.replace('aria-label="\u0627\u0644\u0628\u062d\u062b \u0639\u0646 \u0644\u063a\u0629"', 'aria-label="Search language"')
content = content.replace('aria-label="\u0627\u0644\u0642\u0627\u0626\u0645\u0629"', 'aria-label="Menu"')
content = content.replace('aria-label="\u0625\u063a\u0644\u0627\u0642 \u0627\u0644\u0642\u0627\u0626\u0645\u0629"', 'aria-label="Close menu"')
content = content.replace('aria-label="\u0642\u0627\u0626\u0645\u0629 \u0627\u0644\u062c\u0648\u0627\u0644"', 'aria-label="Mobile menu"')
content = content.replace('aria-label="\u0627\u0644\u0631\u0626\u064a\u0633\u064a\u0629"', 'aria-label="Home"')

# Write back
with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print("HTML attributes fixed!")
print(f"File size: {len(content)} chars, {content.count(chr(10))+1} lines")
