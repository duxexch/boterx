import re, subprocess, html as H

html_src = open('/tmp/dash_live.html', encoding='utf-8').read()
blocks = re.findall(r'<script(?![^>]*src=)[^>]*>(.*?)</script>', html_src, re.S)
print("inline scripts found:", len(blocks))
for i, b in enumerate(blocks):
    src = H.unescape(b)
    if not src.strip():
        print(f'--- script #{i}: (empty)')
        continue
    p = f'/tmp/inline_{i}.js'
    open(p, 'w', encoding='utf-8').write(src)
    r = subprocess.run(['node', '--check', p], capture_output=True, text=True)
    status = 'OK' if r.returncode == 0 else 'SYNTAX ERROR'
    print(f'--- script #{i} ({len(src)} chars): {status}')
    if r.returncode != 0:
        print(r.stderr[:800])
        lines = src.split('\n')
        print('>>> first 5 lines of broken script:')
        print('\n'.join(lines[:5])[:500])
