import sys,io,re
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace')
with open('dashboard/templates/landing.html','r',encoding='utf-8') as f:
    content=f.read()

scripts=re.findall(r'<script[^>]*>(.*?)</script>',content,re.DOTALL)
script1=scripts[1]
print('Script 1 length:', len(script1))

# Find all } positions
for i, ch in enumerate(script1):
    if ch == '}':
        # Show context
        ctx=script1[max(0,i-30):i+10]
        print(f'  }} at {i}: {repr(ctx)}')
