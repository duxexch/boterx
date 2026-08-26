import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
c = open('dashboard/static/js/admin-phrases.js', encoding='utf-8').read()
print('admin-phrases.js entries:', c.count('"') // 2)
c2 = open('dashboard/static/js/app.js', encoding='utf-8').read()
print('app.js size:', len(c2))
# Check for syntax errors by looking for common issues
if c.count('{') != c.count('}'):
    print('WARNING: braces mismatch in admin-phrases.js')
else:
    print('admin-phrases.js braces OK')
