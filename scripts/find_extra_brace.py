import sys,io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace')
with open('dashboard/templates/landing.html','r',encoding='utf-8') as f:
    content=f.read()
idx=content.rfind('footer_responsible:')
chunk=content[idx:idx+100]
print('Last footer_responsible:', repr(chunk[:80]))
# Find };  after it
semi=content.find('};',idx)
print('};  at:', semi)
print('Around };  :', repr(content[semi:semi+30]))
