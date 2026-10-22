"""托盘图标：GDI 手绘「小卡片 + 数字 + 电量条」。

做法：
1. 先在 4 倍画布上画两遍同样的几何——一遍纯白（当 alpha 蒙版），一遍真彩色；
2. 盒式降采样后用蒙版去 alpha，得到边缘平滑、颜色正确的图标。
所以既能做圆角透明，也能保住数字和色条的层次。
"""
import ctypes
import struct
import time
import winreg
from ctypes import wintypes as w

gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)


class ICONINFO(ctypes.Structure):
    _fields_ = [("fIcon", w.BOOL), ("xHotspot", w.DWORD), ("yHotspot", w.DWORD),
                ("hbmMask", w.HANDLE), ("hbmColor", w.HANDLE)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", w.DWORD), ("biWidth", w.LONG), ("biHeight", w.LONG),
                ("biPlanes", w.WORD), ("biBitCount", w.WORD),
                ("biCompression", w.DWORD), ("biSizeImage", w.DWORD),
                ("biXPelsPerMeter", w.LONG), ("biYPelsPerMeter", w.LONG),
                ("biClrUsed", w.DWORD), ("biClrImportant", w.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", w.DWORD * 3)]


class RECT(ctypes.Structure):
    _fields_ = [("left", w.LONG), ("top", w.LONG), ("right", w.LONG), ("bottom", w.LONG)]


gdi32.CreateCompatibleDC.restype = w.HDC
gdi32.CreateCompatibleDC.argtypes = [w.HDC]
gdi32.CreateDIBSection.restype = w.HANDLE
gdi32.CreateDIBSection.argtypes = [w.HDC, ctypes.POINTER(BITMAPINFO), w.UINT,
                                   ctypes.POINTER(ctypes.c_void_p), w.HANDLE, w.DWORD]
gdi32.CreateBitmap.restype = w.HANDLE
gdi32.CreateBitmap.argtypes = [ctypes.c_int, ctypes.c_int, w.UINT, w.UINT, ctypes.c_void_p]
gdi32.SelectObject.restype = w.HANDLE
gdi32.SelectObject.argtypes = [w.HDC, w.HANDLE]
gdi32.CreateSolidBrush.restype = w.HANDLE
gdi32.CreateSolidBrush.argtypes = [w.DWORD]
gdi32.CreatePen.restype = w.HANDLE
gdi32.CreatePen.argtypes = [ctypes.c_int, ctypes.c_int, w.DWORD]
gdi32.GetStockObject.restype = w.HANDLE
gdi32.GetStockObject.argtypes = [ctypes.c_int]
gdi32.RoundRect.argtypes = [w.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                            ctypes.c_int, ctypes.c_int, ctypes.c_int]
gdi32.Rectangle.argtypes = [w.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
gdi32.DeleteObject.argtypes = [w.HANDLE]
gdi32.DeleteDC.argtypes = [w.HDC]
gdi32.CreateFontW.restype = w.HANDLE
gdi32.CreateFontW.argtypes = [ctypes.c_int] * 5 + [w.DWORD] * 8 + [w.LPCWSTR]
gdi32.SetTextColor.argtypes = [w.HDC, w.DWORD]
gdi32.SetBkMode.argtypes = [w.HDC, ctypes.c_int]
user32.DrawTextW.argtypes = [w.HDC, w.LPCWSTR, ctypes.c_int, ctypes.POINTER(RECT), w.UINT]
user32.CreateIconIndirect.restype = w.HANDLE
user32.CreateIconIndirect.argtypes = [ctypes.POINTER(ICONINFO)]
user32.GetSystemMetrics.argtypes = [ctypes.c_int]

SM_CXSMICON = 49
NULL_BRUSH = 5
SUPERSAMPLE = 4

INK = (0x2B, 0x29, 0x26)
CARD = (0xF7, 0xF4, 0xEC)
EDGE = (0xC9, 0xC2, 0xB2)
TRACK = (0xE3, 0xDD, 0xCF)
GOOD = (0x4F, 0x7F, 0x63)
WARN = (0xB0, 0x8A, 0x2F)
BAD = (0xB0, 0x53, 0x48)
TERRA = (0xC2, 0x59, 0x3C)
DIM = (0x9A, 0x95, 0x8A)

_theme = {"light": None, "at": 0.0}


def taskbar_is_light():
    now = time.time()
    if _theme["light"] is not None and now - _theme["at"] < 15:
        return _theme["light"]
    light = False
    try:
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            light = bool(winreg.QueryValueEx(key, "SystemUsesLightTheme")[0])
    except OSError:
        light = False
    _theme.update(light=light, at=now)
    return light


def _pack(c):
    return c[0] | (c[1] << 8) | (c[2] << 16)


def level_rgb(percent):
    if percent is None:
        return DIM
    if percent >= 60:
        return GOOD
    if percent >= 30:
        return WARN
    return BAD


def _new_dib(size):
    dc = gdi32.CreateCompatibleDC(None)
    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = size
    bmi.bmiHeader.biHeight = -size
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bits = ctypes.c_void_p()
    bmp = gdi32.CreateDIBSection(dc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
    gdi32.SelectObject(dc, bmp)
    return dc, bmp, bits


def _paint(size, percent, charging, mask_mode):
    """画一张 size×size 的图；mask_mode=True 时全部用白色（当 alpha 用）。"""
    dc, bmp, bits = _new_dib(size)
    created = []

    def color(c):
        return _pack((255, 255, 255) if mask_mode else c)

    def pen(width, c):
        handle = gdi32.CreatePen(0, width, color(c))
        created.append(handle)
        return handle

    def brush(c):
        handle = gdi32.CreateSolidBrush(color(c))
        created.append(handle)
        return handle

    gdi32.SelectObject(dc, brush((0, 0, 0)))
    gdi32.SelectObject(dc, pen(0, (0, 0, 0)))
    gdi32.Rectangle(dc, 0, 0, size + 1, size + 1)

    pad = max(1, int(size * 0.03))
    radius = max(3, int(size * 0.26))
    edge = max(1, int(size * 0.045))

    gdi32.SelectObject(dc, brush(CARD))
    gdi32.SelectObject(dc, pen(edge, EDGE))
    gdi32.RoundRect(dc, pad, pad, size - pad, size - pad, radius, radius)

    # 电量条
    bar_h = max(2, int(size * 0.10))
    bar_y1 = size - pad - max(1, int(size * 0.10))
    bar_y0 = bar_y1 - bar_h
    bx0 = pad + max(1, int(size * 0.12))
    bx1 = size - pad - max(1, int(size * 0.12))
    gdi32.SelectObject(dc, brush(TRACK))
    gdi32.SelectObject(dc, pen(1, TRACK))
    gdi32.RoundRect(dc, bx0, bar_y0, bx1, bar_y1, bar_h, bar_h)

    if percent is not None and (percent > 0 or charging):
        tone = TERRA if charging else level_rgb(percent)
        span = bx1 - bx0
        fill_w = int(span * max(0, min(100, int(percent))) / 100.0)
        fill_w = max(fill_w, bar_h)
        gdi32.SelectObject(dc, brush(tone))
        gdi32.SelectObject(dc, pen(1, tone))
        gdi32.RoundRect(dc, bx0, bar_y0, bx0 + fill_w, bar_y1, bar_h, bar_h)

    # 数字
    text = "—" if percent is None else str(int(percent))
    digits = len(text)
    if digits >= 3:
        want = int(size * 0.42)
    elif digits == 2:
        want = int(size * 0.52)
    else:
        want = int(size * 0.56)
    font = gdi32.CreateFontW(-want, 0, 0, 0, 700, 0, 0, 0, 0, 0, 0, 0, 0, "Segoe UI")
    created.append(font)
    gdi32.SelectObject(dc, font)
    gdi32.SetBkMode(dc, 1)                       # TRANSPARENT
    gdi32.SetTextColor(dc, color(INK))
    rect = RECT(int(size * 0.02), int(size * 0.06), int(size * 0.98),
                bar_y0 - int(size * 0.02))
    user32.DrawTextW(dc, text, -1, ctypes.byref(rect),
                     0x0001 | 0x0004 | 0x0020)    # CENTER | VCENTER | SINGLELINE

    raw = ctypes.string_at(bits, size * size * 4)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(dc)
    for handle in created:
        gdi32.DeleteObject(handle)
    return raw


def _downsample(src, big, small):
    step = big // small
    out = bytearray(small * small * 4)
    for y in range(small):
        for x in range(small):
            b = g = r = a = 0
            for dy in range(step):
                row = (y * step + dy) * big * 4
                for dx in range(step):
                    i = row + (x * step + dx) * 4
                    b += src[i]
                    g += src[i + 1]
                    r += src[i + 2]
            n = step * step
            o = (y * small + x) * 4
            out[o] = b // n
            out[o + 1] = g // n
            out[o + 2] = r // n
            out[o + 3] = 255
    return bytes(out)


def make_battery_icon(percent, charging=False, dim=False, size=None, dump=None):
    """返回 HICON（调用方负责 DestroyIcon）。charging 用橙色电量条提示。"""
    if size is None:
        size = user32.GetSystemMetrics(SM_CXSMICON) or 16
    size = max(16, min(64, int(size * 1.6)))

    big = size * SUPERSAMPLE
    mask_raw = _paint(big, percent, charging, mask_mode=True)
    color_raw = _paint(big, percent, charging, mask_mode=False)

    mask = mask_raw
    color = color_raw

    # alpha = 蒙版亮度（白色区域不透明），颜色取彩色那一遍
    big_out = bytearray(len(mask_raw))
    for i in range(0, len(mask_raw), 4):
        a = mask[i] if mask[i] > mask[i + 1] else mask[i + 1]
        if mask[i + 2] > a:
            a = mask[i + 2]
        if dim:
            a = a * 3 // 5
        big_out[i] = color[i]
        big_out[i + 1] = color[i + 1]
        big_out[i + 2] = color[i + 2]
        big_out[i + 3] = a
    if charging:
        # 充电时电量条走橙色，提示“在充电”
        pass

    pixels = bytearray(_downsample(bytes(big_out), big, size))
    # 降采样后 alpha 用蒙版单独算，边缘更准
    mask_small = _downsample(mask_raw, big, size)
    for i in range(0, len(pixels), 4):
        a = mask_small[i] if mask_small[i] > mask_small[i + 1] else mask_small[i + 1]
        if mask_small[i + 2] > a:
            a = mask_small[i + 2]
        pixels[i + 3] = a * 3 // 5 if dim else a

    if dump:
        _save_bmp(dump, bytes(pixels), size)

    dc, bmp, bits = _new_dib(size)
    ctypes.memmove(bits, bytes(pixels), len(pixels))
    mask_bmp = gdi32.CreateBitmap(size, size, 1, 1, None)
    info = ICONINFO()
    info.fIcon = True
    info.hbmMask = mask_bmp
    info.hbmColor = bmp
    hicon = user32.CreateIconIndirect(ctypes.byref(info))
    gdi32.DeleteObject(mask_bmp)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(dc)
    return hicon


def _save_bmp(path, pixels, size, scale=8, bg=(32, 32, 32)):
    rows = []
    for y in range(size):
        line = bytearray()
        for x in range(size):
            i = (y * size + x) * 4
            b, g, r, a = pixels[i], pixels[i + 1], pixels[i + 2], pixels[i + 3]
            line += bytes((b * a // 255 + bg[2] * (255 - a) // 255,
                           g * a // 255 + bg[1] * (255 - a) // 255,
                           r * a // 255 + bg[0] * (255 - a) // 255, 255)) * scale
        rows.extend([bytes(line)] * scale)
    data = b"".join(rows)
    with open(path, "wb") as f:
        f.write(b"BM")
        f.write(struct.pack("<IHHI", 54 + len(data), 0, 0, 54))
        f.write(struct.pack("<IiiHHIIiiII", 40, size * scale, -size * scale,
                            1, 32, 0, len(data), 0, 0, 0, 0))
        f.write(data)
