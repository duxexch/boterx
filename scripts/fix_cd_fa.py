import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

path = r'C:\Users\gnz\Downloads\boterx-dev\dashboard\templates\company_detail.html'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Add detail_page_title and detail_desc to fa block
fa_insert = '    detail_page_title: "\u0645\u0648\u0627\u0642\u0639\u0647 \u06a9\u0627\u0645\u0644 {company}",\n    detail_desc: "\u0645\u0648\u0627\u0642\u0639\u0647 \u06a9\u0627\u0645\u0644 {company} - \u0645\u062c\u0648\u0632\u060c \u0648\u06cc\u0698\u06af\u06cc\u200c\u0647\u0627\u060c \u0645\u0632\u0627\u06cc\u0627\u060c \u0639\u06cc\u0628\u0627\u0646\u06cc\u200c\u0647\u0627\u060c \u06a9\u062f \u062a\u0628\u0644\u06cc\u063a\u0627\u062a\u06cc \u0648 \u0644\u06cc\u0646\u06a9 \u0631\u062c\u0633\u062a\u0631 \u0628\u0627 \u0634\u0645\u0627\u0631\u0647 VEX.",\n'

# Find fa block's footer_copyright
fa_start = content.find('  fa: {')
if fa_start > 0:
    # Find footer_copyright in fa block
    fa_section = content[fa_start:fa_start+5000]
    footer_idx = fa_section.find('    footer_copyright:')
    if footer_idx > 0:
        abs_idx = fa_start + footer_idx
        content = content[:abs_idx] + fa_insert + content[abs_idx:]
        print("Added detail_page_title + detail_desc to fa block")
    else:
        print("ERROR: footer_copyright not found in fa block")

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"File updated: {len(content)} chars")
