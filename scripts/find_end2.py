import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
with open('dashboard/templates/landing.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the exact text around the es block end
search = 'footer_responsible:'
idx = content.rfind(search)  # Last occurrence
print(f'Last footer_responsible at idx {idx}')
chunk = content[idx-5:idx+120]
print(repr(chunk))

# Try to find the closing pattern
pattern = content[idx:idx+200]
# Find };\n or };\n
for i, c in enumerate(pattern):
    if c == '}' and i < 50:
        print(f'Close brace at offset {i}: {repr(pattern[i:i+10])}')
