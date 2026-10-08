content = open('dashboard/templates/channels.html', 'r', encoding='utf-8').read()

ai_start = content.find('🧠 AI Agents')
next_tab = content.find('<!-- TAB: Report -->')

print("AI start:", ai_start)
print("Next tab:", next_tab)
print("Distance:", next_tab - ai_start)

# Find the AI tab div start
ai_tab_start = content.rfind('<div x-show="tab ===', 0, ai_start + 100)
print("AI tab div start:", ai_tab_start)

# Find the section between AI tab start and next tab
section = content[ai_tab_start:content.find('<!-- TAB: Report -->')]
print("Section length:", len(section))

# Find the closing </div> of the AI tab
depth = 0
in_tag = False
for i, c in enumerate(content[ai_tab_start:]):
    if c == '<' and i+1 < len(content[ai_tab_start:]) and content[ai_tab_start+i+1] != '/':
        if i+4 < len(content[ai_tab_start:]) and content[ai_tab_start+i+1:i+5] == 'div':
            depth += 1
    elif c == '<' and i+1 < len(content[ai_tab_start:]) and content[ai_tab_start+i+1] == '/':
        if i+5 < len(content[ai_tab_start:]) and content[ai_tab_start+i+1:i+6] == '/div>':
            depth -= 1
            if depth == 0:
                abs_pos = ai_tab_start + i + 6
                print("Found closing </div> at position:", ai_tab_start + i + 6)
                print("Content after:", content[abs_pos:abs_pos+100])
                break

print("AI start:", ai_start)
print("Next tab:", content.find('<!-- TAB: Report -->'))