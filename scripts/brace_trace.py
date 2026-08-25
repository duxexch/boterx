src = open('tmp_js/inline_1.js', encoding='utf-8').read()
depth = 0
in_str = None
in_template = False
in_line_comment = False
in_block_comment = False
prev = ''
line = 1
events = []
i = 0
while i < len(src):
    c = src[i]
    if c == '\n':
        line += 1
        in_line_comment = False
    elif in_line_comment:
        pass
    elif in_block_comment:
        if prev == '*' and c == '/':
            in_block_comment = False
    elif in_str == "'":
        if c == "'" and prev != '\\':
            in_str = None
    elif in_str == '"':
        if c == '"' and prev != '\\':
            in_str = None
    elif in_template:
        if c == '`' and prev != '\\':
            in_template = False
    else:
        if prev == '/' and c == '/':
            in_line_comment = True
        elif prev == '/' and c == '*':
            in_block_comment = True
        elif c == "'":
            in_str = "'"
        elif c == '"':
            in_str = '"'
        elif c == '`':
            in_template = True
        elif c == '{':
            depth += 1
            if depth <= 3:
                events.append((line, depth, 'OPEN'))
        elif c == '}':
            depth -= 1
            if depth <= 3:
                events.append((line, depth, 'CLOSE'))
    prev = c
    i += 1

print(f"final depth: {depth}")
print("events (first 60):")
for e in events[:60]:
    print(e)