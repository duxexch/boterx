content = open('dashboard/templates/channels.html', 'r', encoding='utf-8').read()

# Find AI tab div start
ai_tab_start = content.rfind('<div x-show="tab === \'ai\'', 0, 50000)
print("AI tab div start:", ai_tab_start)

# Find the end of this div by parsing
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
    if c == '"':
        in_string = not in_string
        continue
    if in_string:
        continue
    
    if c == '<' and i+5 < len(content[ai_tab_start:]) and content[ai_tab_start+i+1:ai_tab_start+i+6] == '/div>':
        if depth == 0:
            abs_pos = ai_tab_start + i + 6
            print("Found end at absolute pos:", abs_pos)
            print("Context:", content[abs_pos-50:abs_pos+100])
            break
        depth -= 1
    elif c == '<' and i+4 < len(content[ai_tab_start:]) and content[ai_tab_start+i+1:ai_tab_start+i+4] == 'div':
        depth += 1

if depth != 0:
    print("Final depth:", depth)