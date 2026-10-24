"""打印某进程的窗口树（含子窗口），找出真正的 UI 窗口。"""
import ctypes
import sys
from ctypes import wintypes as w

user32 = ctypes.WinDLL("user32")
pid_target = int(sys.argv[1])


class RECT(ctypes.Structure):
    _fields_ = [("l", w.LONG), ("t", w.LONG), ("r", w.LONG), ("b", w.LONG)]


def info(hwnd):
    cls = ctypes.create_unicode_buffer(96)
    user32.GetClassNameW(hwnd, cls, 96)
    title = ctypes.create_unicode_buffer(96)
    user32.GetWindowTextW(hwnd, title, 96)
    rect = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    owner = w.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
    return (f"  hwnd={hex(hwnd)} cls={cls.value[:30]!r} title={title.value[:16]!r} "
            f"{rect.r - rect.l}x{rect.b - rect.t} pid={owner.value} vis={bool(user32.IsWindowVisible(hwnd))}")


def walk(hwnd, depth=0):
    print("  " * depth + info(hwnd))
    kids = []

    def cb(child, _):
        kids.append(child)
        return True

    user32.EnumChildWindows(hwnd, ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)(cb), 0)
    for child in kids:
        walk(child, depth + 1)


tops = []


def cb(hwnd, _):
    owner = w.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
    if owner.value == pid_target:
        tops.append(hwnd)
    return True


user32.EnumWindows(ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)(cb), 0)
for hwnd in tops:
    walk(hwnd)
