"""Minimal ASAR extractor (stdlib only).

Usage: python asar_extract.py <app.asar> <outdir> [pattern]
"""
import json
import os
import struct
import sys


def read_header(f):
    # asar: 4-byte uint32 = 4, 4-byte uint32 = header_pickle_size,
    # then pickle: uint32 payload_size, uint32 type, uint32 string_len, json...
    f.seek(0)
    (_, hdr_size) = struct.unpack("<II", f.read(8))
    f.seek(12)
    (json_len,) = struct.unpack("<I", f.read(4))
    data = f.read(json_len)
    return json.loads(data.decode("utf-8")), 8 + hdr_size


def walk(node, prefix=""):
    for name, meta in node.get("files", {}).items():
        path = prefix + "/" + name if prefix else name
        if "files" in meta:
            yield from walk(meta, path)
        else:
            yield path, meta


def main():
    src, out = sys.argv[1], sys.argv[2]
    pattern = sys.argv[3].lower() if len(sys.argv) > 3 else None
    with open(src, "rb") as f:
        header, base = read_header(f)
        entries = list(walk(header))
        print(f"{len(entries)} files, data starts at {base}")
        if pattern:
            shown = 0
            for path, meta in entries:
                if pattern in path.lower():
                    print(f"  {path}  {meta.get('size')}  off={base + int(meta.get('offset', 0))}")
                    shown += 1
            print(f"{shown} matched")
            return
        for path, meta in entries:
            target = os.path.join(out, path.replace("/", os.sep))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            f.seek(base + int(meta.get("offset", 0)))
            with open(target, "wb") as g:
                g.write(f.read(int(meta["size"])))
        print("extracted to", out)


if __name__ == "__main__":
    main()
