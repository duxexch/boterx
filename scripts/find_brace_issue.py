import sys,io,re
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace')
with open('dashboard/templates/landing.html','r',encoding='utf-8') as f:
    content=f.read()

scripts = re.findall(r'<script[^>]*>(.*?)</script>', content, re.DOTALL)
for i, script in enumerate(scripts):
    if i == 1:
        print(f'Script {i} ({len(script)} chars):')
        print(script[:300])
        print('...')
        print(script[-200:])
        # Find the imbalance
        depth = 0
        for j, ch in enumerate(script):
            if ch == '{': depth += 1
            elif ch == '}': depth -= 1
            if depth < 0:
                print(f'  Extra closing brace at position {j}: ...{script[max(0,j-30):j+30]}...')
                break
        if depth > 0:
            print(f'  Missing {depth} closing braces')
        elif depth == 0:
            print('  Braces balanced')
