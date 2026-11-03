"""验证标语（充电态）与键盘图对齐。"""
import json
import threading
import time

import hidlib
import protocols
import webview

html = open(r"C:\Users\citie\peripheral-battery\ui\index.html", encoding="utf-8").read()
win = webview.create_window("chk", html=html, width=1000, height=680)

res = protocols.read_all(hidlib.enumerate_interfaces())
for r in res:
    r.pop("alt", None)
STATE = {"interval": 300, "autostart": True, "busy": False, "selected": 0,
         "devices": res}

CASES = [
    (19, True, "低电量充电"),
    (68, True, "中电量充电"),
    (98, True, "快充满"),
    (68, False, "正常"),
    (19, False, "低电量未充"),
    (45, False, "中等未充"),
]


def probe():
    time.sleep(2.5)
    print("设备:", [(r["name"], r["percent"], r["charging"]) for r in res])

    print("\n标语逻辑（pct / charging -> 文案）:")
    for pct, chg, label in CASES:
        win.evaluate_js(
            "render(%s); 1" % json.dumps(
                {**STATE, "devices": [
                    {**res[0], "percent": pct, "charging": chg},
                    res[1]]}, ensure_ascii=False))
        time.sleep(0.35)
        a = win.evaluate_js("document.getElementById('h1a').textContent")
        b = win.evaluate_js("document.getElementById('h1b').textContent")
        print(f"  {pct:>3}% charging={str(chg):5s} ({label:8s}) -> {a}{b}")

    print("\n键盘图:")
    win.evaluate_js("render(%s); 1" % json.dumps(STATE, ensure_ascii=False))
    time.sleep(0.6)
    print("  元素数:", win.evaluate_js("document.querySelectorAll('#art rect').length"))
    print("  viewBox:", win.evaluate_js("document.querySelector('#art svg').getAttribute('viewBox')"))
    bbox = win.evaluate_js(
        "JSON.stringify(document.querySelector('#art svg').getBoundingClientRect())")
    print("  实际渲染框:", bbox)
    win.destroy()


threading.Thread(target=probe, daemon=True).start()
webview.start()

