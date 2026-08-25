content = open('dashboard/templates/channels.html', 'r', encoding='utf-8').read()

ai_tab_start = content.rfind('<div x-show="tab === \'ai\'', 0, 50000)
next_tab = content.find('<!-- TAB: Report -->')

print("AI tab div start:", ai_start)
print("Next tab:", next_tab)

# Find the exact end of AI tab div by finding the matching closing </div>
ai_tab_start = content.rfind('<div x-show="tab === \'ai\'', 0, 50000)

# Parse to find matching closing </div>
depth = 0
in_string = False
escape = False
end_pos = -1

for i, c in enumerate(content[ai_tab_start:]):
    if escape:
        escape = False
        continue
    if c == '\\':
        escape = True
        continue
    if c == '"' and not escape:
        in_string = not in_string
        continue
    if in_string:
        continue
    
    if c == '<' and i+5 < len(content[ai_tab_start:]) and content[ai_tab_start+i+1:i+6] == '/div>':
        if depth == 0:
            end_pos = ai_tab_start + i + 6
            break
        depth -= 1
    elif c == '<' and i+4 < len(content[ai_tab_start:]) and content[ai_tab_start+i+1:i+4] == 'div':
        depth += 1

if end_pos != -1:
    print("Found end at:", end_pos)
    print("Context:", content[end_pos-50:end_pos+50])
    
    # Now replace from ai_tab_start to end_pos
    with open('ai_agent_section_new.html', 'r', encoding='utf-8') as f:
        new_content = f.read()
    
    new_html = content[:ai_tab_start] + new_section + content[end_pos:]
    
    with open('dashboard/templates/channels.html', 'w', encoding='utf-8') as f:
        f.write(new_html)
    print("Replacement done!")
else:
    print("Could not find end")