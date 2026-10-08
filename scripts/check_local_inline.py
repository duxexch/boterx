import re, subprocess, html as H, os

src = open('dashboard/templates/base.html', encoding='utf-8').read()
blocks = re.findall(r'<script(?![^>]*src=)[^>]*>(.*?)</script>', src, re.S)
print("inline scripts found:", len(blocks))
os.makedirs('tmp_js', exist_ok=True)
all_ok = True
for i, b in enumerate(blocks):
    code = H.unescape(b)
    if not code.strip():
        print(f'--- script #{i}: (empty)')
        continue
    # skip jinja templates
    if '{{' in code or '{%' in code:
        print(f'--- script #{i}: SKIP (jinja)')
        continue
    p = f'tmp_js/inline_{i}.js'
    open(p, 'w', encoding='utf-8').write(code)
    r = subprocess.run(['node', '--check', p], capture_output=True, text=True)
    status = 'OK' if r.returncode == 0 else 'SYNTAX ERROR'
    if r.returncode != 0:
        all_ok = False
        print(f'--- script #{i} ({len(code)} chars): {status}')
        print(r.stderr[:600])
    else:
        print(f'--- script #{i} ({len(code)} chars): {status}')

print('\nALL OK' if all_ok else '\nERRORS FOUND')