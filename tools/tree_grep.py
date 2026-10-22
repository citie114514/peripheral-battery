"""Grep every .js/.json under a dir, writing utf-8 output to a file."""
import os
import re
import sys

root = sys.argv[1]
out_path = sys.argv[2]
pats = sys.argv[3:]
maxhits = 5
ctx = 160

files = []
for base, _dirs, names in os.walk(root):
    for n in names:
        if n.lower().endswith((".js", ".json", ".mjs")):
            files.append(os.path.join(base, n))

out = open(out_path, "w", encoding="utf-8")
for pat in pats:
    out.write(f"\n######## {pat!r}\n")
    total = 0
    for f in files:
        try:
            txt = open(f, "r", encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        hits = [m.start() for m in re.finditer(re.escape(pat), txt, re.I)]
        if not hits:
            continue
        total += len(hits)
        out.write(f"  -- {os.path.relpath(f, root)} ({len(hits)})\n")
        for i in hits[:maxhits]:
            out.write("     ..." + txt[max(0, i - ctx): i + ctx].replace("\n", " ") + "\n")
    out.write(f"  total {total}\n")
out.close()
print("written", out_path)
