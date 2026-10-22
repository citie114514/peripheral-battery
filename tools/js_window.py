"""Dump a readable window of minified JS around a pattern (crude beautify)."""
import re
import sys

path, pattern = sys.argv[1], sys.argv[2]
before = int(sys.argv[3]) if len(sys.argv) > 3 else 4000
after = int(sys.argv[4]) if len(sys.argv) > 4 else 12000

text = open(path, "r", encoding="utf-8", errors="replace").read()
i = text.find(pattern)
if i < 0:
    i = text.lower().find(pattern.lower())
if i < 0:
    print("pattern not found")
    sys.exit(1)

chunk = text[max(0, i - before): i + after]
# crude beautify: newline after statement/brace separators that are not inside strings
out = []
depth = 0
in_str = None
prev = ""
for ch in chunk:
    if in_str:
        out.append(ch)
        if ch == in_str and prev != "\\":
            in_str = None
        prev = ch
        continue
    if ch in "\"'`":
        in_str = ch
        out.append(ch)
    elif ch == "{":
        depth += 1
        out.append("{\n" + "  " * depth)
    elif ch == "}":
        depth = max(0, depth - 1)
        out.append("\n" + "  " * depth + "}")
    elif ch == ";":
        out.append(";\n" + "  " * depth)
    elif ch == "," and depth == 0:
        out.append(",\n")
    else:
        out.append(ch)
    prev = ch

print(f"--- window at {i} ---")
print("".join(out))
