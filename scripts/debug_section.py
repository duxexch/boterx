content = open('dashboard/templates/channels.html', 'r', encoding='utf-8').read()

ai_start = content.find('🧠 AI Agents')
next_tab = content.find('<!-- TAB: Report -->')

print("AI start:", ai_start)
print("Next tab:", next_tab)
print("Distance:", next_tab - ai_start)

# Find the AI section boundaries more carefully
section = content[ai_start:next_tab]
print("Section length:", len(section))

# Find the last </div> before the next tab that closes the AI tab
# The structure is: <div x-show="tab === 'ai'" ...> ... </div>
# Find the last </div> before the next tab marker
last_div = content.rfind('</div>', 0, next_tab)
print("Last </div> before next tab:", next_tab - last_div, "chars before next tab")

# Check the structure around the AI tab
section_start = content.rfind('<div x-show="tab === \'ai\'', 0, next_tab)
print("AI tab div start:", ai_start - section_start if section_start > ai_start else "before AI text")

# Let's look at the actual content around AI agents
section_preview = content[ai_start-200:next_tab]
print("--- PREVIEW ---")
print(section_preview[:2000])