"""假休眠期间：读接收器版本 + 试「让接收器重新拉起键盘」的指令。

思路：既然接收器知道键盘状态（state=05），它可能有「重连/唤醒配对设备」的指令。
在 0xFF60 / 0xFF00 两个通道上试一批候选命令，看哪个能让键盘重新应答 0x10。
"""
import time

import hidlib
from probe1k import Chan

VID, PID = 0x36B0, 0x3002


def open_ch(ifaces, up):
    rec = hidlib.find_interface(ifaces, VID, PID, up)
    if rec is None:
        return None, None
    total = 33 if up == 0xFF60 else 64
    return rec, Chan(rec.path, total, total)


def awake(ifaces):
    """键盘醒着 = 0x10 能拿到 0x55。"""
    rec, ch = open_ch(ifaces, 0xFF60)
    if ch is None or not ch.ok:
        return None
    try:
        buf = bytearray(33)
        buf[1] = 0xAA
        buf[2] = 0x10
        buf[5] = 0x18
        ch.write(bytes(buf))
        end = time.time() + 0.8
        while time.time() < end:
            data = ch.read(250)
            if not data:
                continue
            f = data[1:] if data[0] == 0x00 else data
            if len(f) > 7 and f[0] == 0xAA and f[1] == 0x10:
                return f[7]
    finally:
        ch.close()
    return None


def main():
    ifaces = hidlib.enumerate_interfaces()
    st = awake(ifaces)
    print(f"键盘状态: {'0x%02X 醒着' % st if st == 0x55 else '无回应（假休眠）'}")

    # 1) 接收器版本：0xFF60 上 B3（之前抓到过固件字符串）
    rec, ch = open_ch(ifaces, 0xFF60)
    if ch and ch.ok:
        for cmd in (0xB3, 0xB2, 0xB1):
            buf = bytearray(33)
            buf[1] = cmd
            ch.write(bytes(buf))
            end = time.time() + 0.6
            while time.time() < end:
                data = ch.read(200)
                if not data:
                    continue
                printable = "".join(chr(b) if 32 <= b < 127 else "." for b in data[:22])
                print(f"  cmd 0x{cmd:02X} -> {printable}")
                break
        ch.close()

    # 2) 候选「重连/唤醒」指令
    print("\n试候选重连指令（每轮后测键盘是否醒）:")
    cands = [
        ("0xD1", 0xFF60, 0xD1), ("0xD2", 0xFF60, 0xD2),
        ("0xB4", 0xFF60, 0xB4), ("0xB5", 0xFF60, 0xB5),
        ("0xB6", 0xFF60, 0xB6), ("0xB7", 0xFF60, 0xB7),
        ("0xB8", 0xFF60, 0xB8), ("0xB9", 0xFF60, 0xB9),
        ("0xBA", 0xFF60, 0xBA), ("0xBB", 0xFF60, 0xBB),
        ("0xBC", 0xFF60, 0xBC), ("0xBD", 0xFF60, 0xBD),
        ("0xBE", 0xFF60, 0xBE), ("0xBF", 0xFF60, 0xBF),
        ("0xD0 len=0", 0xFF60, 0xD0),
    ]
    for name, up, cmd in cands:
        rec, ch = open_ch(ifaces, up)
        if ch is None or not ch.ok:
            continue
        try:
            buf = bytearray(33 if up == 0xFF60 else 64)
            buf[1] = 0xAA if up == 0xFF60 else 0xAA
            buf[2] = cmd
            buf[5] = 0x18
            ch.write(bytes(buf))
            time.sleep(0.35)
        finally:
            ch.close()
        st = awake(hidlib.enumerate_interfaces())
        mark = "★ 醒了！" if st == 0x55 else "仍无回应"
        print(f"  {name:12s} -> {mark}")
        if st == 0x55:
            return


if __name__ == "__main__":
    main()
