import sys,io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace')
with open('dashboard/templates/landing.html','r',encoding='utf-8') as f:
    content=f.read()

# Check en block translations for company descriptions
en_start=content.find('  en: {')
en_end=content.find('\n  fr: {')
en_block=content[en_start:en_end]

for key in ['comp_desc_1xbet','comp_desc_melbet','comp_desc_default','vex_desc','vex_services_val','vex_support_val','vex_security_val']:
    idx=en_block.find(key+':')
    if idx>0:
        end=en_block.find('\n',idx)
        line=en_block[idx:end]
        print(f'{key}: {line[:120]}')
    else:
        print(f'{key}: NOT FOUND')
print()

# Check the 1XBET span - is it closed?
idx=content.find('comp_desc_1xbet')
if idx>0:
    span_end=content.find('</span>',idx)
    elif_marker='{% elif'
    next_close=content.find(elif_marker,idx)
    print(f'comp_desc_1xbet span end: {span_end}, elif at: {next_close}')
    if span_end>0 and next_close>0:
        if span_end < next_close:
            print('OK: span closed before elif')
        else:
            print('PROBLEM: span not closed before elif!')

# Check MELBET span
idx=content.find('comp_desc_melbet')
if idx>0:
    span_end=content.find('</span>',idx)
    else_marker='{% else'
    next_close=content.find(else_marker,idx)
    print(f'comp_desc_melbet span end: {span_end}, else at: {next_close}')
    if span_end>0 and next_close>0:
        if span_end < next_close:
            print('OK: span closed before else')
        else:
            print('PROBLEM: span not closed before else!')
