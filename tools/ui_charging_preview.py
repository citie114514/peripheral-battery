"""渲染「充电中」状态并截图。"""
import json
import threading
import time

import webview

html = open(r"C:\Users\citie\peripheral-battery\ui\index.html", encoding="utf-8").read()
win = webview.create_window("充电中预览", html=html, width=1000, height=680)

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
    time.sleep(3)
    win.evaluate_js(f"render({json.dumps(STATE, ensure_ascii=False)}); 'ok'")
    time.sleep(30)


threading.Thread(target=probe, daemon=True).start()
webview.start()

