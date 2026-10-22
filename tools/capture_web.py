"""启动 WebView2 界面并截屏（用桌面抓取，能拍到 WebView 子窗口内容）。"""
import ctypes
import os
import struct
import subprocess
import sys
import time
from ctypes import wintypes as w

user32 = ctypes.WinDLL("user32")
gdi32 = ctypes.WinDLL("gdi32")

# 让捕获进程按物理像素工作，否则在 150% 缩放下量到的是虚拟坐标
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass

user32.SetWindowPos.argtypes = [w.HWND, w.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, w.UINT]


class RECT(ctypes.Structure):
    _fields_ = [("left", w.LONG), ("top", w.LONG), ("right", w.LONG), ("bottom", w.LONG)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", w.DWORD), ("biWidth", w.LONG), ("biHeight", w.LONG),
                ("biPlanes", w.WORD), ("biBitCount", w.WORD), ("biCompression", w.DWORD),
                ("biSizeImage", w.DWORD), ("biXPelsPerMeter", w.LONG),
                ("biYPelsPerMeter", w.LONG), ("biClrUsed", w.DWORD),
                ("biClrImportant", w.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", w.DWORD * 3)]


def find_window(pid):
    hits = []

    def cb(hwnd, _):
        owner = w.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            rect = RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            width, height = rect.right - rect.left, rect.bottom - rect.top
            if width > 500 and height > 400:
                hits.append((width * height, hwnd, rect))
        return True

    user32.EnumWindows(ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)(cb), 0)
    hits.sort(reverse=True)
    return hits[0][1:] if hits else (None, None)


def grab(rect, path):
    width, height = rect.right - rect.left, rect.bottom - rect.top
    screen = user32.GetDC(0)
    mem = gdi32.CreateCompatibleDC(screen)
    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = width
    bmi.bmiHeader.biHeight = -height
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bits = ctypes.c_void_p()
    bmp = gdi32.CreateDIBSection(mem, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
    gdi32.SelectObject(mem, bmp)
    gdi32.BitBlt(mem, 0, 0, width, height, screen, rect.left, rect.top, 0x00CC0020)
    data = ctypes.string_at(bits, width * height * 4)
    with open(path, "wb") as f:
        f.write(b"BM")
        f.write(struct.pack("<IHHI", 54 + len(data), 0, 0, 54))
        f.write(struct.pack("<IiiHHIIiiII", 40, width, -height, 1, 32, 0, len(data), 0, 0, 0, 0))
        f.write(data)
    return width, height


def main():
    subprocess.run(["taskkill", "/F", "/IM", "python.exe", "/FI", "PID ne %d" % os.getpid()],
                   capture_output=True)
    subprocess.run(["taskkill", "/F", "/IM", "pythonw.exe"], capture_output=True)
    time.sleep(1.5)
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    args = [sys.executable, "periph_battery.py"] + sys.argv[1:]
    proc = subprocess.Popen(args, cwd=r"C:\Users\citie\peripheral-battery", env=env,
                            stdout=subprocess.DEVNULL, stderr=open(
                                r"C:\Users\citie\peripheral-battery\download\web_err.txt", "w"))
    for _ in range(40):
        time.sleep(0.5)
        hwnd, rect = find_window(proc.pid)
        if hwnd:
            break
    else:
        print("no window; stderr:")
        print(open(r"C:\Users\citie\peripheral-battery\download\web_err.txt").read()[:1200])
        proc.kill()
        return 1

    time.sleep(4.5)                       # 等动画跑完
    hwnd, rect = find_window(proc.pid)
    HWND_TOPMOST, HWND_NOTOPMOST, SWP_SHOWWINDOW = -1, -2, 0x40
    user32.SetWindowPos(hwnd, HWND_TOPMOST, rect.left, rect.top,
                        rect.right - rect.left, rect.bottom - rect.top, SWP_SHOWWINDOW)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.8)
    hwnd, rect = find_window(proc.pid)
    size = grab(rect, r"C:\Users\citie\peripheral-battery\download\web.png.bmp")
    user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, 0x0001 | 0x0002)
    print("captured", size, "pid", proc.pid)
    return 0


sys.exit(main())
