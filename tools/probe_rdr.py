"""Probe the PMO RDR receiver battery command, fixing the report-id framing.

The 0xFF00 interface declares ONE output report with id 0x3F and 64 bytes total,
so the buffer handed to WriteFile is [0x3F][0xAA][cmd][offLo][offHi][len]...
Windows strips the id on read, so replies start with 0xAA.
"""
import ctypes
import time

import hid_probe as hp
from probe1k import Chan

VID, PID = 0x36B0, 0x3002
CMD_START, CMD_STOP, CMD_INFO, CMD_FUNC, CMD_BATTERY = 0x10, 0x11, 0x12, 0x14, 0x30


def build(rid, cmd, offset=0, length=24, total=64):
    buf = bytearray(total)
    buf[0] = rid
    buf[1] = 0xAA
    buf[2] = cmd
    buf[3] = offset & 0xFF
    buf[4] = (offset >> 8) & 0xFF
    buf[5] = length
    return bytes(buf)


def hexs(d):
    return " ".join(f"{b:02X}" for b in d)


def main():
    rec = next(r for r in hp.enumerate_hids()
               if r.get("vid") == VID and r.get("pid") == PID
               and r.get("usage_page") == 0xFF00)
    for rid in (0x3F, 0x00):
        print(f"\n### report id 0x{rid:02X}")
        ch = Chan(rec["path"], 64, 64)
        if not ch.ok:
            print("  open failed", ctypes.get_last_error())
            continue
        try:
            for name, cmd in (("start", CMD_START), ("battery", CMD_BATTERY),
                              ("info", CMD_INFO), ("stop", CMD_STOP)):
                ok = ch.write(build(rid, cmd))
                line = f"  {name:8s} write={ok}"
                if ok:
                    data = ch.read(900)
                    if data:
                        line += f"  rx[{len(data)}] {hexs(data[:20])}"
                        if data[0] == 0xAA:
                            line += f"  status=0x{data[7]:02X}"
                            if data[1] == CMD_BATTERY:
                                line += f"  >>> battery={data[8]}% charging={data[9]}"
                    else:
                        line += "  (no reply)"
                print(line)
                time.sleep(0.1)
        finally:
            ch.close()


if __name__ == "__main__":
    main()
