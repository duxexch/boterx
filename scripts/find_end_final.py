content = open('dashboard/templates/channels.html', 'r', encoding='utf-8').read()

ai_tab_start = content.rfind('<div x-show="tab === \'ai\'', 0, 50000)
print('AI tab start:', ai_tab_start)

next_tab = content.find('<!-- TAB: Report -->')
ai_section = content[content.rfind('<div x-show="tab === \'ai\'', 0, 50000):content.find('<!-- TAB: Report -->')]
print('Section length:', len(ai_section))

import re
div_ends = [m.start() for m in re.finditer(r'</div>', ai_section)]
print('Number of </div>:', len(div_ends))

if div_ends:
    ai_tab_start = content.rfind('<div x-show="tab === \'ai\'', 0, 50000)
    abs_end = content.rfind('<div x-show="tab === \'ai\'', 0, 50000) + div_ends[-1] + 6
    print('End position:', abs_end)
    print('Context:', content[abs_end-50:abs_end+50])