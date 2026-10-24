"""盯键盘：关灯后看它多久进入「假休眠」。

每 20 秒采样一次：接收器 0xD0 状态帧、电量、funcInfo（灯光/休眠配置）。
把时间点、能否应答、state_byte、电量、deepSleep 都记录下来。

用法：python tools\watch_sleep.py [采样次数]
"""
import sys
import time

import hidlib
import protocols

ROUNDS = int(sys.argv[1]) if len(sys.argv) > 1 else 15
GAP = 20


def presence(ifaces):
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
                    "pid": f"{data[12] | data[13] << 8:04X}",
                    "state": data[14],
                }
    return None


def main():
    print(f"开始盯 {ROUNDS} 轮，每 {GAP} 秒一次（Ctrl+C 结束）")
    print(f"{'时间':<10} {'接收器':<22} {'电量':<12} {'灯光':<6} {'深休眠':<8} 备注")
    print("-" * 88)

    last_ok = None
    for i in range(ROUNDS):
        ifaces = hidlib.enumerate_interfaces()
        st = presence(ifaces)
        kbd = hidlib.find_interface(ifaces, 0x36B0, 0x3002, 0xFF00)
        res = protocols.read_pmo_keyboard(kbd, interfaces=ifaces)
        info = protocols.read_pmo_funcinfo(kbd, ifaces) if res.get("state") == "ok" else None

        stamp = time.strftime("%H:%M:%S")
        recv = (f"pid={st['pid']} state={st['state']:02X}" if st else "(无回应)")
        battery = (f"{res['percent']}%" if res.get("percent") is not None else "—")
        light = (str(info["light_switch"]) if info else "—")
        deep = (str(info["deep_sleep_minutes"]) if info else "—")
        note = ""
        if res.get("state") == "ok":
            if last_ok is False:
                note = "★ 又醒了"
            last_ok = True
        else:
            note = res.get("detail", "")[:26]
            if last_ok is True:
                note = "★ 刚刚掉线/假休眠 " + note
            last_ok = False
        print(f"{stamp:<10} {recv:<22} {battery:<12} {light:<6} {deep:<8} {note}", flush=True)

        if i < ROUNDS - 1:
            time.sleep(GAP)


if __name__ == "__main__":
    main()
