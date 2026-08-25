content = open('dashboard/templates/channels.html', 'r', encoding='utf-8').read()

ai_start = content.find('🧠 AI Agents')
next_tab = content.find('<!-- TAB: Report -->')

print('AI start:', ai_start)
print('Next tab:', next_tab)

ai_tab_div_start = content.rfind('<div x-show="tab === \'ai\'', 0, 50000)
print('AI tab div start:', ai_tab_div_start)

section = content[ai_start:content.find('<!-- TAB: Report -->')]
print('Section length:', len(section))

with open('ai_section.txt', 'w', encoding='utf-8') as f:
    f.write(section[:5000])

print('Section length:', len(section))