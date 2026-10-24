"""托盘自测：验证「图标消失」的三种情况都能自愈。

1. 正常挂载 → _added == {0,1}
2. 模拟 Explorer 重启（给托盘窗口 PostMessage TaskbarCreated）→ 应重新挂上
3. 模拟图标被通知区踢掉（NIM_DELETE）→ 下一次刷新应退回 NIM_ADD
"""
import ctypes
import time
from ctypes import wintypes as w

import periph_battery as pb
import protocols
from icons import make_battery_icon, user32

runtime = pb.Runtime(debug=True)
runtime.results = [
    dict(protocols.JD_MOUSE, percent=89, charging=False, state="ok", time="20:00"),
    dict(protocols.PMO_KEYBOARD, percent=None, charging=None, state="sleep",
         detail="休眠", time="20:00",
         last={"percent": 93, "charging": False, "time": "19:50"}),
]

t0 = time.time()
icon = make_battery_icon(89)
print(f"画一个图标耗时 {time.time() - t0:.0f} ms")
user32.DestroyIcon(icon)

tray = pb.Tray(runtime)
runtime.tray = tray
tray.start()
print("托盘就绪:", tray.ready.wait(5), "hwnd:", bool(tray.hwnd))
time.sleep(0.5)
print("1) 初次挂载 _added =", sorted(tray._added))

tray.refresh_icons()
time.sleep(0.6)
print("2) 刷新后 _added =", sorted(tray._added), " 图标数 =", len(tray.icons))

# 模拟 Explorer 重启：通知区没了，广播 TaskbarCreated
user32.PostMessageW(tray.hwnd, pb.TASKBAR_CREATED, 0, 0)
time.sleep(0.6)
print("3) TaskbarCreated 之后 _added =", sorted(tray._added))

# 模拟图标被踢：直接删掉，再刷新，应该自动 ADD 回来
for uid in list(tray.icons):
    tray._notify(pb.NIM_DELETE, uid)
tray._added.clear()
tray.refresh_icons()
time.sleep(0.6)
print("4) 被删后再刷新 _added =", sorted(tray._added))

user32.PostMessageW(tray.hwnd, pb.WM_DESTROY, 0, 0)
tray.join(3)
print("5) 线程已退出:", not tray.is_alive())
