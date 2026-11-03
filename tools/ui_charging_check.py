"""用真实设备数据渲染，检查每张卡片的 charging class 是否正确。"""
import json
import threading
import time

import hidlib
import protocols
import webview

html = open(r"C:\Users\citie\peripheral-battery\ui\index.html", encoding="utf-8").read()
win = webview.create_window("charging-check", html=html, width=1000, height=680)

results = protocols.read_all(hidlib.enumerate_interfaces())
for r in results:
    r.pop("alt", None)
STATE = {"interval": 60, "autostart": True, "busy": False, "selected": 0,
         "devices": results}


def probe():
    time.sleep(2.5)
    win.evaluate_js(f"render({json.dumps(STATE, ensure_ascii=False)}); 'ok'")
    time.sleep(25)
    print("真实数据:")
    for r in results:
        print(f"  {r['name']:12s} {r['percent']}%  charging={r['charging']}")
    print("\n卡片渲染结果:")
    n = win.evaluate_js("document.querySelectorAll('.dcard').length")
    for i in range(int(n)):
        cls = win.evaluate_js(f"document.querySelectorAll('.dcard')[{i}].className")
        name = win.evaluate_js(
            f"document.querySelectorAll('.dcard')[{i}].querySelector('.nm').textContent")
        tag = win.evaluate_js(
            f"getComputedStyle(document.querySelectorAll('.dcard')[{i}]"
            f".querySelector('.chgTag')).display")
        print(f"  {name:12s} class={cls!r} chgTag={tag}")
    print("\nhero 区:")
    print("  hero class:", win.evaluate_js("document.getElementById('hero').className"))
    print("  胶囊:", win.evaluate_js("document.getElementById('chipText').textContent"))
    time.sleep(1)


threading.Thread(target=probe, daemon=True).start()
webview.start()

