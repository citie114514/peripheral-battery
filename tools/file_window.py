"""Dump windows around patterns in a single file (crude beautify, utf-8 out)."""
import re
import sys

path = sys.argv[1]
out_path = sys.argv[2]
specs = sys.argv[3:]  # pattern:before:after

text = open(path, "r", encoding="utf-8", errors="replace").read()
out = open(out_path, "w", encoding="utf-8")

for spec in specs:
    parts = spec.split(":")
    pat = parts[0]
    before = int(parts[1]) if len(parts) > 1 else 400
    after = int(parts[2]) if len(parts) > 2 else 1200
    idxs = [m.start() for m in re.finditer(re.escape(pat), text)]
    out.write(f"\n\n######## {pat!r} ({len(idxs)} hits)\n")
    for i in idxs[:4]:
        out.write(f"--- at {i} ---\n")
        out.write(text[max(0, i - before): i + after] + "\n")
out.close()
print("written", out_path)
