"""直接打电量命令（不等 START 的 ack），两个接口各刷 6 次，看会不会回。"""
import time

import hid_probe as hp
from probe1k import Chan

rows = [r for r in hp.enumerate_hids()
        if r.get("vid") == 0x36B0 and r.get("pid") == 0x3002
        and r.get("usage_page") in (0xFF00, 0xFF60)]

for rec in rows:
    up = rec["usage_page"]
    total = 64 if up == 0xFF00 else 33
    rid = 0x3F if up == 0xFF00 else 0x00
    ch = Chan(rec["path"], total, 64)
    if not ch.ok:
        print(f"up=0x{up:04X} 打开失败")
        continue
    print(f"\n=== up=0x{up:04X} rid=0x{rid:02X} total={total}")
    for attempt in range(6):
        buf = bytearray(total)
        buf[0] = rid
        buf[1] = 0xAA
        buf[2] = 0x30
        buf[5] = 24
        ch.write(bytes(buf))
        end = time.time() + 0.5
        got = False
        while time.time() < end:
            data = ch.read(200)
            if not data:
                continue
            body = " ".join(f"{b:02X}" for b in data[:20])
            frame = data[1:] if data[0] == rid else data
            tag = " <== 命中" if len(frame) > 2 and frame[0] == 0xAA and frame[1] == 0x30 else ""
            print(f"  try{attempt}: {body}{tag}")
            got = True
        if not got and attempt == 0:
            print("  (无回应)")
    ch.close()
