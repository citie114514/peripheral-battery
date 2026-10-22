"""列出某个进程的所有窗口（类名/标题/尺寸/可见），用于排查 pywebview 窗口。"""
import ctypes
import sys
from ctypes import wintypes as w

u = ctypes.WinDLL("user32")
target = int(sys.argv[1])


class RECT(ctypes.Structure):
    _fields_ = [("l", w.LONG), ("t", w.LONG), ("r", w.LONG), ("b", w.LONG)]


rows = []


def cb(hwnd, _):
    pid = w.DWORD()
    u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value != target:
        return True
    cls = ctypes.create_unicode_buffer(80)
    u.GetClassNameW(hwnd, cls, 80)
    title = ctypes.create_unicode_buffer(120)
    u.GetWindowTextW(hwnd, title, 120)
    rect = RECT()
    u.GetWindowRect(hwnd, ctypes.byref(rect))
    rows.append((hex(hwnd), cls.value[:34], title.value[:22],
                 rect.r - rect.l, rect.b - rect.t, bool(u.IsWindowVisible(hwnd))))
    return True


u.EnumWindows(ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)(cb), 0)
for row in rows:
    print(row)
