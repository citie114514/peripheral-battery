"""刷固件后的回归测试：盯 state 字节，确认不再出现假休眠（05）。

每 15 秒采样一次，记录 state / 电量 / 能否握手。
出现 state=05 或握手无回应就标红报警。

用法：python tools\regress_sleep.py [分钟数]
"""
import sys
import time

import hidlib
import protocols

MINUTES = int(sys.argv[1]) if len(sys.argv) > 1 else 5
GAP = 15


def sample():
    ifaces = hidlib.enumerate_interfaces()
    presence = protocols._pmo_presence(ifaces)
    alive, state = presence if presence else (None, 0)
    kbd = hidlib.find_interface(ifaces, 0x36B0, 0x3002, 0xFF00)
    res = protocols.read_pmo_keyboard(kbd, interfaces=ifaces)
    return {
        "paired": alive,
        "state": state,
        "percent": res.get("percent"),
        "state_name": res.get("state"),
        "detail": res.get("detail", ""),
    }


def main():
    rounds = max(1, MINUTES * 60 // GAP)
    print(f"回归测试：{MINUTES} 分钟，每 {GAP} 秒一次")
    print(f"{'时间':<10} {'state':<7} {'电量':<7} {'判定'}")
    print("-" * 60)
    bad = 0
    for i in range(rounds):
        s = sample()
        stamp = time.strftime("%H:%M:%S")
        battery = f"{s['percent']}%" if s["percent"] is not None else "—"
        if s["state"] == protocols.PMO_STATE_FAKE_SLEEP:
            verdict = "★ 假休眠复发（state=05）"
            bad += 1
        elif s["percent"] is None:
            verdict = "休眠/无回应：" + (s["detail"] or "")[:26]
        else:
            verdict = "正常"
        print(f"{stamp:<10} {s['state']:02X}      {battery:<7} {verdict}", flush=True)
        if i < rounds - 1:
            time.sleep(GAP)
    print("-" * 60)
    print("结果:", "★ 仍有问题" if bad else "✓ 全程未出现假休眠")


if __name__ == "__main__":
    main()
