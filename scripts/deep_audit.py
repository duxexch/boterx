import sys,io,re
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace')
with open('dashboard/templates/landing.html','r',encoding='utf-8') as f:
    content=f.read()

# Check for JS syntax errors - find the IIFE
iife_start=content.find('(function(){')
iife_end=content.find('})();')
iife=content[iife_start:iife_end+4]
print('IIFE length:', len(iife))

# Check for any JS error patterns
if 'undefined' in iife.split('\n')[0:3]:
    print('WARNING: undefined reference')

# Check the EN block thoroughly
en_start=content.find('  en: {')
fr_start=content.find('\n  fr: {')
en_block=content[en_start:fr_start]
keys=re.findall(r'    (\w+):', en_block)
print('EN keys count:', len(keys))

# Check for problematic quotes in EN block
single_quotes = en_block.count("'")
print('Single quotes in EN block:', single_quotes)

# Check for unclosed strings
for i, line in enumerate(en_block.split('\n')):
    stripped = line.strip()
    if stripped.startswith('//') or stripped.startswith('/*'):
        continue
    # Check balanced quotes
    dq = stripped.count('"') - stripped.count('\\"')
    if dq % 2 != 0:
        print(f'  UNBALANCED double quotes at line {i}: {stripped[:60]}')

# Count data-i18n elements
data_i18n_count = len(re.findall(r'data-i18n="', content))
print(f'data-i18n elements in HTML: {data_i18n_count}')

# Check if any data-i18n elements appear inside Jinja loops (company cards)
comp_section = content[content.find('comp-grid'):content.find('</section>', content.find('comp-grid'))]
loop_data_i18n = re.findall(r'data-i18n="([^"]+)"', comp_section)
print(f'data-i18n inside company card loop: {len(loop_data_i18n)}')
print(f'  Keys: {set(loop_data_i18n)}')
