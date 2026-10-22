import re, sys

path = sys.argv[1]
text = open(path, "r", encoding="utf-8", errors="replace").read()
print("chars", len(text))

pats = sys.argv[2:]
for p in pats:
    ms = [m.start() for m in re.finditer(re.escape(p), text, re.I)]
    print(f"\n### {p!r}: {len(ms)} hits")
    seen = set()
    for i in ms[:8]:
        chunk = text[max(0, i - 150): i + 250].replace("\n", " ")
        key = chunk[:80]
        if key in seen:
            continue
        seen.add(key)
        print("   ...", chunk)
