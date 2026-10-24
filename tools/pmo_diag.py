"""PMO P75 的「假休眠」诊断。

读三样东西：
1. 接收器 0xD0 状态帧里的末字节（连接/工作模式位）
2. RDR funcInfo：灯光开关、亮度、sleepTime、deepSleepTime
3. 电量能不能读到（能读 = 键盘其实醒着）

用法（先在键盘上按几下唤醒它）：
    python tools\\pmo_diag.py
"""
import time

import hidlib
import protocols


def presence_byte(ifaces):
    iface = hidlib.find_interface(ifaces, 0x36B0, 0x3002, 0xFF60)
    if iface is None:
        return None
    with iface.open(read=True, write=True) as h:
        if not h.ok:
            return None
        h.drain()
        buf = bytearray(33)
        buf[1] = 0xAA
        buf[2] = 0xD0
        buf[5] = 0x18
        if not h.write_raw(buf):
            return None
        end = time.time() + 0.8
        while time.time() < end:
            data = h.read(250)
            if data and len(data) >= 15 and data[1] == 0xAA and data[2] == 0xD0:
                return {
                    "raw": " ".join(f"{b:02X}" for b in data[:16]),
                    "count": data[9],
                    "vid": f"{data[10] | data[11] << 8:04X}",
                    "pid": f"{data[12] | data[13] << 8:04X}",
                    "state_byte": data[14],
                }
    return None


def main():
    ifaces = hidlib.enumerate_interfaces()
    print("=== 接收器状态（0xD0）===")
    st = presence_byte(ifaces)
    print(st if st else "(无回应)")

    print("\n=== 电量（能读到说明键盘醒着）===")
    res = protocols.read_pmo_keyboard(
        hidlib.find_interface(ifaces, 0x36B0, 0x3002, 0xFF00), interfaces=ifaces)
    print({k: res[k] for k in ("percent", "charging", "state", "detail")})

    print("\n=== funcInfo（灯光 / 休眠配置）===")
    info = protocols.read_pmo_funcinfo(
        hidlib.find_interface(ifaces, 0x36B0, 0x3002, 0xFF00), ifaces)
    if not info:
        print("(读不到)")
        return
    for key in ("light_switch", "light_mode", "brightness", "speed",
                "sleep_minutes", "deep_sleep_minutes", "scan_delay"):
        print(f"  {key:20s} {info[key]}")
    print("  raw:", info["raw"])


if __name__ == "__main__":
    main()
