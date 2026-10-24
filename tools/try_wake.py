"""假休眠能不能被配置指令叫醒？

在「接收器说连着（state=05）但键盘不应答」的状态下，依次尝试各种帧，
看哪一种能让 0x10 握手重新拿到 0x55。

用法：python tools\try_wake.py
"""
import time

import hidlib
from probe1k import Chan

VID, PID = 0x36B0, 0x3002


def frame(cmd, off=0, ln=24, mark=0xAA):
    buf = bytearray(33)
    buf[1] = mark
    buf[2] = cmd
    buf[3] = off & 0xFF
    buf[4] = (off >> 8) & 0xFF
    buf[5] = ln
    return bytes(buf)


def probe(ifaces):
    """握手能不能拿到 0x55。"""
    rec = hidlib.find_interface(ifaces, VID, PID, 0xFF60)
    if rec is None:
        return None
    ch = Chan(rec.path, 33, 33)
    if not ch.ok:
        return None
    try:
        ch.write(frame(0x10))
        end = time.time() + 0.8
        while time.time() < end:
            data = ch.read(250)
            if not data:
                continue
            f = data[1:] if data[0] == 0x00 else data
            if len(f) > 7 and f[0] == 0xAA and f[1] == 0x10:
                return f[7]          # 0x55 = 醒着
    finally:
        ch.close()
    return None


WAKE_TRIES = [
    ("0xD0 状态轮询", [frame(0xD0, 0, 0x18)]),
    ("0x10 连发 5 次", [frame(0x10)] * 5),
    ("0x12 设备信息", [frame(0x12, 0, 56)]),
    ("0x14 funcInfo", [frame(0x14, 0, 24)]),
    ("0x30 电池", [frame(0x30, 0, 24)]),
    ("0x10+0x30 组合", [frame(0x10), frame(0x30, 0, 24)]),
    ("全零帧", [bytes(33)]),
    ("0xAA 单字节", [bytes([0x00, 0xAA]) + bytes(31)]),
]


def main():
    ifaces = hidlib.enumerate_interfaces()
    rec = hidlib.find_interface(ifaces, VID, PID, 0xFF60)
    if rec is None:
        print("没找到接收器")
        return
    status = probe(ifaces)
    print(f"当前握手状态: {'0x%02X（醒着）' % status if status else '无回应（假休眠）'}")
    if status == 0x55:
        print("键盘已经醒着，先关灯等它睡着再跑这个脚本")
        return

    ch = Chan(rec.path, 33, 33)
    try:
        for name, frames in WAKE_TRIES:
            for f in frames:
                ch.write(f)
                time.sleep(0.12)
            time.sleep(0.5)
            st = probe(hidlib.enumerate_interfaces())
            print(f"  {name:16s} -> {'0x%02X 醒了！' % st if st == 0x55 else ('0x%02X' % st if st else '仍无回应')}")
            if st == 0x55:
                print(f"\n★ 有效唤醒方式：{name}")
                return
    finally:
        ch.close()
    print("\n都不行——只能切模式重连（固件 bug 坐实）")


if __name__ == "__main__":
    main()

