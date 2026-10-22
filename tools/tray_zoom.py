"""截任务栏右侧（托盘区）并放大，检查图标长相。"""
import ctypes
import struct
import time
from ctypes import wintypes as w

ctypes.windll.shcore.SetProcessDpiAwareness(2)
user32 = ctypes.WinDLL("user32")
gdi32 = ctypes.WinDLL("gdi32")


class BIH(ctypes.Structure):
    _fields_ = [("biSize", w.DWORD), ("biWidth", w.LONG), ("biHeight", w.LONG),
                ("biPlanes", w.WORD), ("biBitCount", w.WORD), ("biCompression", w.DWORD),
                ("biSizeImage", w.DWORD), ("biXPelsPerMeter", w.LONG),
                ("biYPelsPerMeter", w.LONG), ("biClrUsed", w.DWORD),
                ("biClrImportant", w.DWORD)]


class BI(ctypes.Structure):
    _fields_ = [("bmiHeader", BIH), ("bmiColors", w.DWORD * 3)]


sw, sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
W, Hh, scale = 460, 56, 4
x, y = sw - W - 8, sh - Hh
screen = user32.GetDC(0)
mem = gdi32.CreateCompatibleDC(screen)
bi = BI()
bi.bmiHeader.biSize = ctypes.sizeof(BIH)
bi.bmiHeader.biWidth = W
bi.bmiHeader.biHeight = -Hh
bi.bmiHeader.biPlanes = 1
bi.bmiHeader.biBitCount = 32
bits = ctypes.c_void_p()
bmp = gdi32.CreateDIBSection(mem, ctypes.byref(bi), 0, ctypes.byref(bits), None, 0)
gdi32.SelectObject(mem, bmp)
gdi32.BitBlt(mem, 0, 0, W, Hh, screen, x, y, 0x00CC0020)
src = ctypes.string_at(bits, W * Hh * 4)

rows = []
for row in range(Hh):
    line = src[row * W * 4:(row + 1) * W * 4]
    big = bytearray()
    for col in range(W):
        big += line[col * 4:col * 4 + 4] * scale
    rows.extend([bytes(big)] * scale)
data = b"".join(rows)
out = r"C:\Users\citie\peripheral-battery\download\tray_zoom.bmp"
with open(out, "wb") as f:
    f.write(b"BM")
    f.write(struct.pack("<IHHI", 54 + len(data), 0, 0, 54))
    f.write(struct.pack("<IiiHHIIiiII", 40, W * scale, -Hh * scale, 1, 32, 0,
                        len(data), 0, 0, 0, 0))
    f.write(data)
print("saved", out, sw, sh)
