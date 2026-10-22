"""验证界面在「休眠」状态下渲染上次读数（不需要看屏幕，直接读 DOM 文本）。"""
import json
import threading
import time

import webview

html = open(r"C:\Users\citie\peripheral-battery\ui\index.html", encoding="utf-8").read()
win = webview.create_window("verify", html=html, width=1000, height=680)

STATE = {
    "interval": 60,
    "autostart": False,
    "busy": False,
    "selected": 0,
    "devices": [
        {"key": "mouse", "name": "贱驴 RSR5S", "source": "Ultra-Link 8K 接收器",
         "vid": 0x362D, "pid": 0xD028, "found": True, "percent": None,
         "charging": None, "state": "sleep", "time": "12:40:00",
         "detail": "接收器无回应（鼠标已休眠，动一下鼠标就更新）",
         "last": {"percent": 90, "charging": False, "time": "12:31:02"}},
        {"key": "keyboard", "name": "PMO P75", "source": "RDR 2.4G 接收器",
         "vid": 0x36B0, "pid": 0x3002, "found": True, "percent": None,
         "charging": None, "state": "idle", "time": "12:40:00",
         "detail": "键盘已配对但不响应电量查询"},
    ],
}


def probe():
    time.sleep(2.5)
    print(win.evaluate_js(f"render({json.dumps(STATE, ensure_ascii=False)}); 'ok'"))
    time.sleep(0.8)
    checks = {
        "数字": win.evaluate_js("document.getElementById('pct').textContent"),
        "胶囊": win.evaluate_js("document.getElementById('chipText').textContent"),
        "副标题": win.evaluate_js("document.getElementById('sub').textContent"),
        "引语": win.evaluate_js("document.getElementById('quote').textContent"),
        "卡片胶囊": win.evaluate_js("document.querySelectorAll('.dcard .pill')[0].textContent"),
        "休眠样式": win.evaluate_js("document.querySelectorAll('.dcard')[0].className"),
    }
    for k, v in checks.items():
        print(f"  {k}: {v}")
    win.destroy()


threading.Thread(target=probe, daemon=True).start()
webview.start()
