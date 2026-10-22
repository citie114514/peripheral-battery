"""Hook PMO HUB's own WebHID traffic via CDP and dump the frames.

  1. launch PMO HUB with --remote-debugging-port
  2. Page.addScriptToEvaluateOnNewDocument(<hook>) so the hook lands before app JS
  3. Page.reload -> the app connects to the keyboard and talks
  4. poll window.__hidTrace and print it
"""
import json
import os
import subprocess
import sys
import time

from cdp_client import WS, find_target

PORT = 9333
EXE = r"C:\Users\citie\AppData\Local\Programs\PMOHub\PMOHub.exe"

HOOK = r"""
window.__hidTrace = window.__hidTrace || [];
(function () {
  function hex(u8) {
    try {
      return Array.from(new Uint8Array(u8.buffer ? u8.buffer : u8, u8.byteOffset || 0))
        .map(function (b) { return b.toString(16).padStart(2, '0'); }).join(' ');
    } catch (e) { return '<bad>'; }
  }
  function tag(d) { return (d.vendorId|0).toString(16) + ':' + (d.productId|0).toString(16) + ' ' + (d.productName||''); }
  function push() { window.__hidTrace.push(Array.prototype.slice.call(arguments)); }
  var P = HIDDevice.prototype;
  ['sendReport', 'sendFeatureReport', 'receiveFeatureReport', 'sendOutputReport'].forEach(function (name) {
    var orig = P[name];
    if (!orig) return;
    P[name] = function () {
      var a = arguments;
      var data = a.length > 1 ? hex(a[1]) : '';
      push(name, tag(this), 'rid=' + a[0], data);
      return orig.apply(this, a);
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
    env = dict(os.environ)
    env.pop("ELECTRON_RUN_AS_NODE", None)
    proc = subprocess.Popen([EXE, f"--remote-debugging-port={PORT}"], env=env)
    print("launched pid", proc.pid)
    pages = find_target(PORT)
    if not pages:
        print("no CDP page target")
        return
    print("target:", pages[0]["url"][:80])
    ws = WS(pages[0]["webSocketDebuggerUrl"])
    ws.call("Page.enable")
    ws.call("Runtime.enable")
    ws.call("Page.addScriptToEvaluateOnNewDocument", {"source": HOOK})
    ws.call("Page.reload", {"ignoreCache": False})
    print("hook installed, reloaded; waiting for traffic…")
    for step in range(24):
        time.sleep(2)
        try:
            res = ws.call("Runtime.evaluate", {
                "expression": "JSON.stringify((window.__hidTrace||[]).slice(-40))",
                "returnByValue": True,
            })
            val = res.get("result", {}).get("value")
            if val and val not in ("[]", "null"):
                print(f"\n--- tick {step} ---")
                for row in json.loads(val):
                    print("  ", " | ".join(str(x) for x in row)[:220])
        except Exception as e:
            print("poll error", e)
    print("\ndone")


if __name__ == "__main__":
    main()
