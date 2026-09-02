import sys,io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace')
with open('dashboard/templates/landing.html','r',encoding='utf-8') as f:
    content=f.read()

# The IIFE
iife_start=content.find('(function(){')
iife_end=content.find('})();',iife_start)+5
iife=content[iife_start:iife_end]
print('IIFE length:', len(iife))
print('Last 100 chars:', repr(iife[-100:]))
print()

# Count braces in IIFE
opens=iife.count('{')
closes=iife.count('}')
print('Braces: { =', opens, '} =', closes)

# Check ALL script blocks for brace balance
import re
scripts=re.findall(r'<script[^>]*>(.*?)</script>',content,re.DOTALL)
for i,s in enumerate(scripts):
    if len(s.strip())<10: continue
    o=s.count('{')
    c=s.count('}')
    if o!=c:
        print(f'Script {i}: UNBALANCED {o} {{ vs {c} }}')
        # Find the problem area
        depth=0
        for j,ch in enumerate(s):
            if ch=='{': depth+=1
            elif ch=='}': depth-=1
            if depth<0:
                print(f'  Extra }} at pos {j}: ...{s[max(0,j-40):j+40]}...')
                break
