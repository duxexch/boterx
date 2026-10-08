import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

path = r'C:\Users\gnz\Downloads\boterx-dev\dashboard\templates\landing.html'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# FIX 1: Fix broken span tags for company descriptions
# Line 2033: 1XBET missing </span> before {% elif
old_1xbet = '{% elif c.name == \'MELBET\' %}<span data-i18n="comp_desc_melbet">'
# First close the 1XBET span
content = content.replace(
    '130%.\n          {% elif c.name',
    '130%.</span>\n          {% elif c.name'
)
print("FIXED: 1XBET span closing tag")

# Line 2034: MELBET missing </span> before {% else
content = content.replace(
    'cekod {{ c.promo_code or \'VEX\' }}.\n          {% else %}',
    'cekod {{ c.promo_code or \'VEX\' }}.</span>\n          {% else %}'
)
print("FIXED: MELBET span closing tag")

# FIX 2: Fix currentLang default text
content = content.replace(
    'id="currentLang">العربية</span>',
    'id="currentLang">English</span>'
)
print("FIXED: currentLang default to English")

# FIX 3: Fix duplicate placeholder
content = content.replace(
    'placeholder="Search language..." placeholder="Search language..."',
    'placeholder="Search language..."'
)
print("FIXED: duplicate placeholder")

# FIX 4: Fix lang-list button text-align for LTR
content = content.replace(
    '.lang-list button{display:flex;align-items:center;gap:12px;width:100%;padding:12px 14px;background:transparent;border:none;color:var(--text);font-size:15px;text-align:right;cursor:pointer',
    '.lang-list button{display:flex;align-items:center;gap:12px;width:100%;padding:12px 14px;background:transparent;border:none;color:var(--text);font-size:15px;text-align:left;cursor:pointer'
)
print("FIXED: lang-list text-align left for LTR")

# FIX 5: Fix close button text
content = content.replace('aria-label="\u0625\u063a\u0644\u0627\u0642 Menu"', 'aria-label="Close menu"')
print("FIXED: close button aria-label")

# FIX 6: Fix the IIFE to use textContent for most elements and innerHTML only for elements with HTML
old_iife_start = """  document.querySelectorAll('[data-i18n]').forEach(function(e){
      var key=e.getAttribute('data-i18n');
      if(t[key]) e.innerHTML=t[key];
    });"""

new_iife_start = """  var htmlKeys=['hero_title','hero_badge','faq_a1','faq_a2','faq_a3','faq_a4','step2_desc'];
    document.querySelectorAll('[data-i18n]').forEach(function(e){
      var key=e.getAttribute('data-i18n');
      if(!t[key])return;
      if(htmlKeys.indexOf(key)>=0){
        e.innerHTML=t[key];
      }else{
        e.textContent=t[key];
      }
    });"""

if old_iife_start in content:
    content = content.replace(old_iife_start, new_iife_start)
    print("FIXED: IIFE uses textContent for plain text, innerHTML for HTML elements")
else:
    print("WARNING: Could not find IIFE to fix")

# Write back
with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"\nFile updated: {len(content)} chars")
