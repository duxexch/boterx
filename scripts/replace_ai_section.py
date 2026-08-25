import re

# Read the template
with open('dashboard/templates/channels.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Read the new AI agent section
with open('scripts/ai_agent_section_new.html', 'r', encoding='utf-8') as f:
    new_section = f.read()

# Find and replace the AI Agents section
# Pattern: from "<div class="bg-slate-800 rounded-xl border border-slate-700 p-4 space-y-3">" containing "🧠 AI Agents" to the closing of that tab
pattern = r'(<div class="bg-slate-800 rounded-xl border border-slate-700 p-4 space-y-3">\s*<div class="flex items-center justify-between"><h3 class="font-bold">🧠 AI Agents</h3>.*?</div>\s*</div>\s*</div>\s*</div>\s*)</div>'

# Find the section - more specific pattern
start_marker = '<div class="bg-slate-800 rounded-xl border border-slate-700 p-4 space-y-3">\n            <div class="flex items-center justify-between"><h3 class="font-bold">🧠 AI Agents</h3>'
end_marker = '</div>\n        </div>\n\n        <!-- TAB: Report -->'

# Find positions
start_idx = content.find(start_marker)
end_idx = content.find('        <!-- TAB: Report -->')

if start_idx != -1 and end_idx != -1:
    # Find the actual end of the AI Agents section (second </div> after the section)
    # We need to find the closing of the AI tab div
    search_start = content.find(start_marker)
    if search_start != -1:
        # Find the closing of the AI tab div
        brace_count = 0
        in_string = False
        escape = False
        end_pos = -1
        
        for i in range(search_start, len(content)):
            c = content[i]
            if escape:
                escape = False
                continue
            if c == '\\' and not escape:
                escape = True
                continue
            if c == '"' and not escape:
                in_string = not in_string
            if not in_string:
                if c == '<' and i+3 < len(content) and content[i+1] == 'd' and content[i+2] == 'i' and content[i+3] == 'v':
                    # Check if this is a closing div
                    if i+5 < len(content) and content[i+1:i+6] == '/div>':
                        # Count backwards to see if we're at the right level
                        pass
            
        # Simpler approach: find the next TAB marker after AI Agents
        ai_agents_start = content.find('<h3 class="font-bold">🧠 AI Agents</h3>')
        if ai_agents_start != -1:
            # Find the next tab start (which is "TAB: Report")
            next_tab = content.find('<!-- TAB: Report -->', ai_agents_start)
            if next_tab != -1:
                # The AI agents section ends just before the next tab
                # Find the last </div> before the next tab
                section_content = content[ai_agents_start:next_tab]
                # Find the last closing divs
                last_div = section_content.rfind('</div>')
                if last_div != -1:
                    actual_end = ai_agents_start + last_div + 6  # +6 for '</div>'
                    # Replace from start of AI section to actual_end
                    new_content = content[:ai_agents_start-100] + new_section + content[actual_end:next_tab] + content[next_tab:]
                    
                    with open('dashboard/templates/channels.html', 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    print("Replacement done!")
                    exit(0)

print("Could not find markers")
print("AI agents start:", content.find('🧠 AI Agents'))
print("Next tab:", content.find('TAB: Report'))