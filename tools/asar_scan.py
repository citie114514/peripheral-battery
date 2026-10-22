import sys, re, io

path = sys.argv[1]
data = open(path, "rb").read()
print("size", len(data))

pats = [b"362D", b"362d", b"36B0", b"36b0", b"0x362d", b"0x36b0", b"Ultra-Link",
        b"Wireless 2.4G", b"35BD", b"35bd", b"25A7", b"D028", b"d028", b"P75", b"Aurora"]

for p in pats:
    idxs = [m.start() for m in re.finditer(re.escape(p), data)]
    print(f"{p!r}: {len(idxs)} hits", idxs[:10])
    for i in idxs[:3]:
        chunk = data[max(0, i - 120): i + 120]
        print("   ", chunk.replace(b"\x00", b".")[:260])
