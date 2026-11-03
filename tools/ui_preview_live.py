"""渲染真实状态并截图（键盘充电中 + 键盘图对齐）。"""
import json
import threading
import time

import hidlib
import protocols
import webview

html = open(r"C:\Users\citie\peripheral-battery\ui\index.html", encoding="utf-8").read()
win = webview.create_window("preview", html=html, width=1000, height=680, resizable=False)

res = protocols.read_all(hidlib.enumerate_interfaces())
for r in res:
    r.pop("alt", None)
STATE = {"interval": 300, "autostart": True, "busy": False, "selected": 1,
         "devices": res}


def probe():
    time.sleep(2.5)
    win.evaluate_js("render(%s); 1" % json.dumps(STATE, ensure_ascii=False))
    time.sleep(40)


threading.Thread(target=probe, daemon=True).start()
webview.start()

