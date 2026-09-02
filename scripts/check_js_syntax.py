import sys,io,re
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace')
with open('dashboard/templates/landing.html','r',encoding='utf-8') as f:
    content=f.read()

# Check ALL script blocks for syntax issues
scripts = re.findall(r'<script[^>]*>(.*?)</script>', content, re.DOTALL)
print(f'Found {len(scripts)} script blocks')

for i, script in enumerate(scripts):
    if len(script.strip()) < 10:
        continue
    # Check for basic JS issues
    # Unclosed braces
    opens = script.count('{')
    closes = script.count('}')
    if opens != closes:
        print(f'  Script {i}: UNBALANCED braces {{ {opens} }} {closes}')
    # Unclosed parens
    opens_p = script.count('(')
    closes_p = script.count(')')
    if opens_p != closes_p:
        print(f'  Script {i}: UNBALANCED parens ( {opens_p} ) {closes_p}')
    # Unclosed brackets
    opens_b = script.count('[')
    closes_b = script.count(']')
    if opens_b != closes_b:
        print(f'  Script {i}: UNBALANCED brackets [ {opens_b} ] {closes_b}')
    if i == len(scripts) - 1:  # Last script block (the one with IIFE)
        print(f'  Script {i} (main): {len(script)} chars, braces OK={opens==closes}, parens OK={opens_p==closes_p}')

# Check the IIFE specifically
iife_idx = content.find('(function(){')
iife_chunk = content[iife_idx:iife_idx+2400]
# Verify the forEach syntax
if '.forEach(function(e)' in iife_chunk:
    print('OK: forEach syntax correct')
# Verify querySelectorAll
if "querySelectorAll('[data-i18n]')" in iife_chunk:
    print('OK: querySelectorAll syntax correct')
