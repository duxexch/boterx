import sys,io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace')
with open('dashboard/templates/landing.html','r',encoding='utf-8') as f:
    content=f.read()

# Find the I18N script
start=content.find('window.I18N_TRANSLATIONS')
end=content.find('};', start) + 2
block=content[start:end]

# Parse carefully - track brace depth through strings
depth=0
in_string=False
escape_next=False
string_char=None

for i, ch in enumerate(block):
    if escape_next:
        escape_next=False
        continue
    if ch == '\\':
        escape_next=True
        continue
    if in_string:
        if ch == string_char:
            in_string=False
        continue
    if ch in ('"', "'"):
        in_string=True
        string_char=ch
        continue
    if ch == '{':
        depth+=1
    elif ch == '}':
        depth-=1
        if depth < 0:
            context=block[max(0,i-50):i+50]
            print(f'EXTRA }} at position {i} in I18N block')
            print(f'Context: {repr(context)}')
            break

if depth > 0:
    print(f'Missing {depth} closing braces')
elif depth == 0:
    print('I18N block braces balanced')
