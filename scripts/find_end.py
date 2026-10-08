import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
with open('dashboard/templates/landing.html', 'r', encoding='utf-8') as f:
    content = f.read()
search = 'Juega Responsablemente'
idx = content.find(search)
if idx >= 0:
    print('Found at idx', idx)
    print(repr(content[idx-30:idx+80]))
else:
    print('NOT FOUND')
