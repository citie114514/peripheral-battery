"""先 0x10 握手，再读 0x14 / 0x12 / 0x30 —— 看握手是不是能解锁其余命令。"""
import time

import hidlib
from probe1k import Chan

ifaces = hidlib.enumerate_interfaces()
rec = hidlib.find_interface(ifaces, 0x36B0, 0x3002, 0xFF60)
ch = Chan(rec.path, 33, 33)
assert ch.ok


def frame(cmd, length=24):
    buf = bytearray(33)
    buf[1] = 0xAA
    buf[2] = cmd
    buf[5] = length
    return bytes(buf)


def send(cmd, length=24, wait=0.7):
    ch.write(frame(cmd, length))
    end = time.time() + wait
    while time.time() < end:
        data = ch.read(200)
        if not data:
            continue
        f = data[1:] if data[0] == 0x00 else data
        if len(f) > 7 and f[0] == 0xAA and f[1] == cmd:
            return f
    return None


start = send(0x10)
print("0x10 握手:", "OK status=0x%02X" % start[7] if start else "失败")

for cmd, ln, name in ((0x14, 41, "funcInfo"), (0x12, 56, "deviceInfo"), (0x30, 24, "battery")):
    got = send(cmd, ln)
    if got:
        print(f"0x{cmd:02X} {name}: status=0x{got[7]:02X} data={' '.join(f'{b:02X}' for b in got[8:8+20])}")
    else:
        print(f"0x{cmd:02X} {name}: 无回复")

# 结束通讯
send(0x11, wait=0.4)
ch.close()
