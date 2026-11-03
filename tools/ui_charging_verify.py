"""验证「充电中」的界面表现：大数字闪电、刻度流光、胶囊、卡片角标。"""
import json
import threading
import time

import webview

html = open(r"C:\Users\citie\peripheral-battery\ui\index.html", encoding="utf-8").read()
win = webview.create_window("verify-charging", html=html, width=1000, height=680)

STATE = {
    "interval": 60, "autostart": True, "busy": False, "selected": 0,
    "devices": [
        {"key": "mouse", "name": "贱驴 RSR5S", "source": "Ultra-Link 8K 接收器",
         "vid": 0x362D, "pid": 0xD028, "found": True, "percent": 68,
         "charging": True, "state": "ok", "time": "21:52:00", "detail": ""},
        {"key": "keyboard", "name": "PMO P75", "source": "RDR 2.4G 接收器",
         "vid": 0x36B0, "pid": 0x3002, "found": True, "percent": 54,
         "charging": True, "state": "ok", "time": "21:52:00", "detail": ""},
    ],
}


def probe():
    time.sleep(2.5)
    print(win.evaluate_js(f"render({json.dumps(STATE, ensure_ascii=False)}); 'ok'"))
    time.sleep(0.6)
    checks = {
        "胶囊文案": win.evaluate_js("document.getElementById('chipText').textContent"),
        "胶囊class": win.evaluate_js("document.getElementById('chip').className"),
        "hero充电态": win.evaluate_js("document.getElementById('hero').className"),
        "刻度充电态": win.evaluate_js("document.getElementById('ruler').className"),
        "闪电可见": win.evaluate_js(
            "getComputedStyle(document.querySelector('.boltBig')).display"),
        "卡片1 class": win.evaluate_js("document.querySelectorAll('.dcard')[0].className"),
        "卡片1角标": win.evaluate_js(
            "getComputedStyle(document.querySelectorAll('.dcard .chgTag')[0]).display"),
    }
    for k, v in checks.items():
        print(f"  {k}: {v}")

    # 切到不充电，确认能收回去
    STATE["devices"][0]["charging"] = False
    STATE["devices"][1]["charging"] = False
    win.evaluate_js(f"render({json.dumps(STATE, ensure_ascii=False)}); 'ok'")
    time.sleep(0.5)
    print("  --- 切回不充电 ---")
    print("  胶囊:", win.evaluate_js("document.getElementById('chipText').textContent"))
    print("  hero:", win.evaluate_js("document.getElementById('hero').className"))
    print("  闪电:", win.evaluate_js(
        "getComputedStyle(document.querySelector('.boltBig')).display"))
    win.destroy()


threading.Thread(target=probe, daemon=True).start()
webview.start()
