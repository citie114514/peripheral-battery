"""盯 PMOHub 的 HID 报文：一直挂着，把每一帧写进 download\\pmo_watch.log。

用法：python tools\\watch_pmo.py
然后用键盘正常打字 1~2 分钟（让键盘醒着），再把 download\\pmo_watch.log 发我。
"""
import json
import os
import subprocess
import time

from cdp_client import WS, find_target

PORT = 9337
EXE = r"C:\Users\citie\AppData\Local\Programs\PMOHub\PMOHub.exe"
OUT = r"C:\Users\citie\peripheral-battery\download\pmo_watch.log"

HOOK = r"""
window.__hidTrace = window.__hidTrace || [];
(function () {
  function hex(u8) {
    try {
      return Array.from(new Uint8Array(u8.buffer ? u8.buffer : u8, u8.byteOffset || 0))
        .map(function (b) { return b.toString(16).padStart(2, '0'); }).join(' ');
    } catch (e) { return '<bad>'; }
  }
  function tag(d) {
    var ups = (d.collections || []).map(function (c) { return c.usagePage + '/' + c.usage; }).join(',');
    return (d.vendorId|0).toString(16) + ':' + (d.productId|0).toString(16) + '[' + ups + ']';
  }
  function push() { window.__hidTrace.push(Array.prototype.slice.call(arguments)); }
  var P = HIDDevice.prototype;
  ['sendReport','sendFeatureReport','receiveFeatureReport','sendOutputReport'].forEach(function (n) {
    var o = P[n];
    if (!o) return;
    P[n] = function () {
      var a = arguments;
      push('SEND:' + n, tag(this), 'rid=' + a[0], a.length > 1 ? hex(a[1]) : '');
      return o.apply(this, a);
    };
  });
  function attach(d) {
    if (d.__hooked) return;
    d.__hooked = true;
    d.addEventListener('inputreport', function (e) {
      push('RECV', tag(e.device), 'rid=' + e.reportId, hex(e.data));
    });
  }
  navigator.hid.addEventListener('connect', function (e) { attach(e.device); });
  navigator.hid.getDevices().then(function (ds) { ds.forEach(attach); });
})();
"""


def main():
    subprocess.run(["taskkill", "/F", "/IM", "PMOHub.exe"], capture_output=True)
    time.sleep(2)
    env = dict(os.environ)
    env.pop("ELECTRON_RUN_AS_NODE", None)
    subprocess.Popen([EXE, f"--remote-debugging-port={PORT}"], env=env)
    pages = find_target(PORT)
    if not pages:
        print("没拿到 CDP 目标")
        return 1
    ws = WS(pages[0]["webSocketDebuggerUrl"])
    ws.call("Page.enable")
    ws.call("Runtime.enable")
    ws.call("Page.addScriptToEvaluateOnNewDocument", {"source": HOOK})
    ws.call("Page.reload")
    print(f"钩子已装，记录写到 {OUT}")
    print("现在去用键盘打字 / 翻 PMOHub 的页面，记录会自动增长（Ctrl+C 结束）")

    seen = set()
    with open(OUT, "w", encoding="utf-8") as out:
        while True:
            time.sleep(1.0)
            try:
                rows = ws.call("Runtime.evaluate", {
                    "expression": "JSON.stringify((window.__hidTrace||[]).slice(-200))",
                    "returnByValue": True}).get("result", {}).get("value")
            except Exception as exc:
                print("轮询出错:", exc)
                return 1
            for row in json.loads(rows or "[]"):
                key = tuple(map(str, row))
                if key in seen:
                    continue
                seen.add(key)
                line = time.strftime("%H:%M:%S ") + " | ".join(key)
                out.write(line + "\n")
                out.flush()
                print(line[:160])


if __name__ == "__main__":
    main()
