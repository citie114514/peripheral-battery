"""抓当前已运行窗口（按标题），DPI 感知。"""
import ctypes
import struct
import sys
from ctypes import wintypes as w

user32 = ctypes.WinDLL("user32")
gdi32 = ctypes.WinDLL("gdi32")
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass


class RECT(ctypes.Structure):
    _fields_ = [("left", w.LONG), ("top", w.LONG), ("right", w.LONG), ("bottom", w.LONG)]


class BIH(ctypes.Structure):
    _fields_ = [("biSize", w.DWORD), ("biWidth", w.LONG), ("biHeight", w.LONG),
                ("biPlanes", w.WORD), ("biBitCount", w.WORD), ("biCompression", w.DWORD),
                ("biSizeImage", w.DWORD), ("biXPelsPerMeter", w.LONG),
                ("biYPelsPerMeter", w.LONG), ("biClrUsed", w.DWORD),
                ("biClrImportant", w.DWORD)]


class BI(ctypes.Structure):
    _fields_ = [("bmiHeader", BIH), ("bmiColors", w.DWORD * 3)]


def main():
    title = sys.argv[2] if len(sys.argv) > 2 else "外设电量"
    out = sys.argv[1] if len(sys.argv) > 1 else "grab.bmp"
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        print("no window")
        return 1
    user32.SetWindowPos.argtypes = [w.HWND, w.HWND, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, w.UINT]
    user32.ShowWindow(hwnd, 9)
    user32.SwitchToThisWindow(hwnd, True)
    user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002)
    user32.SetForegroundWindow(hwnd)
    import time; time.sleep(1.2)
    if user32.GetForegroundWindow() != hwnd:
        print("warn: not foreground")
    rect = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    width, height = rect.right - rect.left, rect.bottom - rect.top
    screen = user32.GetDC(0)
    mem = gdi32.CreateCompatibleDC(screen)
    bi = BI()
    bi.bmiHeader.biSize = ctypes.sizeof(BIH)
    bi.bmiHeader.biWidth = width
    bi.bmiHeader.biHeight = -height
    bi.bmiHeader.biPlanes = 1
    bi.bmiHeader.biBitCount = 32
    bits = ctypes.c_void_p()
    bmp = gdi32.CreateDIBSection(mem, ctypes.byref(bi), 0, ctypes.byref(bits), None, 0)
    gdi32.SelectObject(mem, bmp)
    gdi32.BitBlt(mem, 0, 0, width, height, screen, rect.left, rect.top, 0x00CC0020)
    data = ctypes.string_at(bits, width * height * 4)
    with open(out, "wb") as f:
        f.write(b"BM")
        f.write(struct.pack("<IHHI", 54 + len(data), 0, 0, 54))
        f.write(struct.pack("<IiiHHIIiiII", 40, width, -height, 1, 32, 0, len(data), 0, 0, 0, 0))
        f.write(data)
    user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 0x0001 | 0x0002)
    print("saved", out, width, height)
    return 0


sys.exit(main())

