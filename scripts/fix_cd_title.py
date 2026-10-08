import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

path = r'C:\Users\gnz\Downloads\boterx-dev\dashboard\templates\company_detail.html'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Add detail_page_title and detail_desc keys to each language block
# These are placed before footer_copyright

translations = {
    'ar': {
        'detail_page_title': '\u0645\u0631\u0627\u062c\u0639\u0629 \u0634\u0627\u0645\u0644\u0629 \u0644\u0634\u0631\u0643\u0629 {company}',
        'detail_desc': '\u0645\u0631\u0627\u062c\u0639\u0629 \u0634\u0627\u0645\u0644\u0629 \u0644\u0634\u0631\u0643\u0629 {company} - \u0627\u0644\u062a\u0631\u062e\u064a\u0635\u060c \u0627\u0644\u0645\u0645\u064a\u0632\u0627\u062a\u060c \u0627\u0644\u0639\u064a\u0648\u0628\u060c \u0643\u0648\u062f \u0627\u0644\u0628\u0631\u0648\u0645\u0648 \u0648\u0631\u0627\u0628\u0637 \u0627\u0644\u062a\u0633\u062c\u064a\u0644.',
    },
    'en': {
        'detail_page_title': 'Full Review of {company}',
        'detail_desc': 'Complete review of {company} - license, features, pros, cons, promo code and direct registration link via VEX.',
    },
    'fr': {
        'detail_page_title': 'Avis Complet sur {company}',
        'detail_desc': 'Avis complet sur {company} - licence, fonctionnalit\u00e9s, avantages, inconv\u00e9nients, code promo et lien d\'inscription direct via VEX.',
    },
    'es': {
        'detail_page_title': 'Revisi\u00f3n Completa de {company}',
        'detail_desc': 'Revisi\u00f3n completa de {company} - licencia, caracter\u00edsticas, ventajas, desventajas, c\u00f3digo promocional y enlace de registro directo a trav\u00e9s de VEX.',
    },
    'de': {
        'detail_page_title': 'Vollst\u00e4ndige \u00dcberblick \u00fcber {company}',
        'detail_desc': 'Vollst\u00e4ndige \u00dcbersicht von {company} - Lizenz, Funktionen, Vor- und Nachteile, Promo-Code und direkter Registrierungslink \u00fcber VEX.',
    },
    'it': {
        'detail_page_title': 'Recensione Completa di {company}',
        'detail_desc': 'Recensione completa di {company} - licenza, funzionalit\u00e0, pro, contro, codice promozionale e link di registrazione diretta tramite VEX.',
    },
    'pt': {
        'detail_page_title': 'Revis\u00e3o Completa da {company}',
        'detail_desc': 'Revis\u00e3o completa da {company} - licen\u00e7a, funcionalidades, pr\u00f3s, contras, c\u00f3digo promocional e link de registro direto via VEX.',
    },
    'ru': {
        'detail_page_title': '\u041f\u043e\u043b\u043d\u043e\u0435 \u043e\u0431\u0437\u043e\u0440\u0435\u043d\u0438\u0435 {company}',
        'detail_desc': '\u041f\u043e\u043b\u043d\u043e\u0435 \u043e\u0431\u0437\u043e\u0440\u0435\u043d\u0438\u0435 {company} - \u043b\u0438\u0446\u0435\u043d\u0437\u0438\u044f, \u0444\u0443\u043d\u043a\u0446\u0438\u0438, \u043f\u0440\u043e\u0441\u0442\u0430, \u043c\u0438\u043d\u0443\u0441\u044b, \u043f\u0440\u043e\u043c\u043e-\u043a\u043e\u0434 \u0438 \u043f\u0440\u044f\u043c\u0430\u044f \u0441\u0441\u044b\u043b\u043a\u0430 \u043d\u0430 \u0440\u0435\u0433\u0438\u0441\u0442\u0440\u0430\u0446\u0438\u044e \u0447\u0435\u0440\u0435\u0437 VEX.',
    },
    'zh': {
        'detail_page_title': '{company}\u5b8c\u6574\u8bc4\u6d4b',
        'detail_desc': '{company}\u7684\u5b8c\u6574\u8bc4\u6d4b - \u8bb8\u53ef\u8bc1\u3001\u529f\u80fd\u3001\u4f18\u7f3a\u70b9\u3001\u4f18\u60e0\u7801\u548c\u901a\u8fc7VEX\u7684\u76f4\u63a5\u6ce8\u518c\u94fe\u63a5\u3002',
    },
    'tr': {
        'detail_page_title': '{company} Hakk\u0131nda Tam \u0130nceleme',
        'detail_desc': '{company} hakk\u0131nda tam inceleme - lisans, \u00f6zellikler, art\u0131lar, eksiler, promosyon kodu ve VEX \u00fczerinden do\u011frudan kay\u0131t ba\u011flant\u0131s\u0131.',
    },
    'ur': {
        'detail_page_title': '{company} \u06a9\u0627 \u0645\u0648\u06a9\u0645\u0644 \u062c\u0627\u0693',
        'detail_desc': '{company} \u06a9\u0627 \u0645\u0648\u06a9\u0645\u0644 \u062c\u0627\u0693 - \u0644\u0627\u0626\u0633\u0646\u0633\u060c \u062e\u0635\u0648\u0635\u0627\u062a\u060c \u0641\u0627\u0626\u062f\u06d2\u060c \u0646\u0642\u0627\u0635\u060c \u067e\u0631\u0648\u0645\u0648 \u06a9\u0648\u062f \u0627\u0648\u0631 VEX \u0639\u0628\u0631 \u0645\u0634\u062a\u0631\u06a9 \u0631\u062c\u0633\u062a\u0631 \u0644\u0627\u0646\u06a9\u0602',
    },
    'hi': {
        'detail_page_title': '{company} \u0915\u0940 \u0935\u093f\u0938\u094d\u0924\u093e\u0930 \u0938\u092e\u0940\u0915\u094d\u0937\u0923',
        'detail_desc': '{company} \u0915\u0940 \u0935\u093f\u0938\u094d\u0924\u093e\u0930 \u0938\u092e\u0940\u0915\u094d\u0937\u0923 - \u0932\u093e\u0907\u0938\u0947\u0902\u0938, \u0935\u093f\u0936\u0947\u0937\u0924\u093e\u090f\u0901, \u092b\u093c\u093e\u092f\u0926\u0947, \u0939\u093e\u0928\u093f\u092f\u093e\u0902, \u092a\u094d\u0930\u094b\u092e\u094b \u0915\u094b\u0921 \u0914\u0930 VEX \u0939\u0940\u0902 \u0938\u0947 \u0938\u0940\u0927\u093e \u0930\u091c\u093f\u0938\u094d\u091f\u094d\u0930\u0947\u0936\u0928 \u0932\u093f\u0902\u0915\u0942\u0902.',
    },
    'fa': {
        'detail_page_title': '\u0645\u0648\u0627\u0642\u0639\u0647 \u06a9\u0627\u0645\u0644 {company}',
        'detail_desc': '\u0645\u0648\u0627\u0642\u0639\u0647 \u06a9\u0627\u0645\u0644 {company} - \u0645\u062c\u0648\u0632\u060c \u0648\u06cc\u0698\u06af\u06cc\u200c\u0647\u0627\u060c \u0645\u0632\u0627\u06cc\u0627\u060c \u0639\u06cc\u0628\u0627\u0646\u06cc\u200c\u0647\u0627\u060c \u06a9\u062f \u062a\u0628\u0644\u06cc\u063a\u0627\u062a\u06cc \u0648 \u0644\u06cc\u0646\u06a9 \u0631\u062c\u0633\u062a\u0631 \u0628\u0627 \u0634\u0645\u0627\u0631\u0647 VEX.',
    },
    'id': {
        'detail_page_title': 'Ulasan Lengkap {company}',
        'detail_desc': 'Ulasan lengkap {company} - lisensi, fitur, kelebihan, kekurangan, kode promo, dan tautan pendaftaran langsung melalui VEX.',
    },
    'ja': {
        'detail_page_title': '{company}\u306e\u5b8c\u5168\u306a\u30ea\u30d3\u30e5\u30fc',
        'detail_desc': '{company}\u306e\u5b8c\u5168\u306a\u30ea\u30d3\u30e5\u30fc - \u30e9\u30a4\u30bb\u30f3\u30b9\u3001\u6a5f\u80fd\u3001\u9577\u6240\u3001\u77ed\u6240\u3001\u30d7\u30ed\u30e2\u30b3\u30fc\u30c9\u3001VEX\u7d4c\u7531\u306e\u76f4\u63a5\u767b\u9332\u30ea\u30f3\u30af\u3002',
    },
    'ko': {
        'detail_page_title': '{company} \uc644\uc804 \ud30c\ud06c',
        'detail_desc': '{company}\uc758 \uc644\uc804\ud55c \ud30c\ud06c - \ub77c\uc774\uc2a4\uc5d0\uc2a4, \ud2b9\uc9d5, \uc7a5\uc810, \ub2e4\ud558\uc810, \ud504\ub85c\ubaa8 \ucf54\ub4dc, \ubc14\ub85c VEX\ub97c \ud1b5\ud574 \uc9c4\uc785 \ub9c1\ud06c.',
    },
    'th': {
        'detail_page_title': '\u0e23\u0e32\u0e22\u0e01\u0e32\u0e23\u0e40\u0e1c\u0e35\u0e22\u0e07\u0e2b\u0e31\u0e27 {company}',
        'detail_desc': '\u0e23\u0e32\u0e22\u0e01\u0e32\u0e23\u0e40\u0e1c\u0e35\u0e22\u0e07\u0e2b\u0e31\u0e27 {company} - \u0e22\u0e2d\u0e14\u0e21\u0e07, \u0e04\u0e48\u0e32\u0e2a\u0e39\u0e07\u0e1a\u0e14, \u0e02\u0e48\u0e32\u0e22, \u0e02\u0e49\u0e32\u0e22, \u0e23\u0e2b\u0e31\u0e2a\u0e42\u0e04\u0e23\u0e07 \u0e41\u0e25\u0e49\u0e27\u0e25\u0e48\u0e32\u0e07\u0e17\u0e32\u0e22\u0e40\u0e25\u0e34\u0e28\u0e21\u0e27\u0e49\u0e32\u0e27 VEX.',
    },
}

# Insert before footer_copyright line in each language block
for lang in ['ar', 'en', 'fr', 'es', 'de', 'it', 'pt', 'ru', 'zh', 'tr', 'ur', 'hi', 'fa', 'id', 'ja', 'ko', 'th']:
    # Check if already exists
    if f'detail_page_title:' in content.split(f'  {lang}:')[1].split('};')[0] if f'  {lang}: ' in content else True:
        continue
    
    # Find the footer_copyright line in this language block
    search = f'    footer_copyright:'
    lang_start = content.find(f'  {lang}: {{')
    if lang_start < 0:
        continue
    # Find the next language block or end of I18N
    next_langs = ['ar', 'en', 'fr', 'es', 'de', 'it', 'pt', 'ru', 'zh', 'tr', 'ur', 'hi', 'fa', 'id', 'ja', 'ko', 'th']
    min_next = len(content)
    for nl in next_langs:
        if nl == lang:
            continue
        idx = content.find(f'  {nl}: {{', lang_start + 10)
        if idx > 0 and idx < min_next:
            min_next = idx
    block = content[lang_start:min_next]
    
    footer_idx = block.find('    footer_copyright:')
    if footer_idx < 0:
        continue
    
    # Insert before footer_copyright
    page_title = translations[lang]['detail_page_title']
    desc = translations[lang]['detail_desc']
    insert = f'    detail_page_title: "{page_title}",\n    detail_desc: "{desc}",\n'
    
    abs_idx = lang_start + footer_idx
    content = content[:abs_idx] + insert + content[abs_idx:]
    print(f'Added page_title + desc for {lang}')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print(f'\nFile updated: {len(content)} chars')
