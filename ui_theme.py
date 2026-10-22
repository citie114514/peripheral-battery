"""Claude 风格配色、缓动函数与圆角矩形工具。"""

PAPER = "#F5F1E8"
CARD = "#FDFBF7"
BORDER = "#E4DED1"
INK = "#2B2926"
MUTED = "#8C877D"
TERRA = "#C2593C"
TRACK = "#EDE8DD"

GOOD = "#5F7F63"
WARN = "#A8862F"
BAD = "#B05348"

UI_FONT = "Segoe UI"
UI_FONT_SEMI = "Segoe UI Semibold"
DISPLAY_FONT = "Georgia"


def level_color(percent):
    if percent is None:
        return MUTED
    if percent >= 60:
        return GOOD
    if percent >= 30:
        return WARN
    return BAD


def ease_out_cubic(t):
    return 1 - (1 - t) ** 3


def ease_out_back(t, s=1.4):
    return 1 + (s + 1) * (t - 1) ** 3 + s * (t - 1) ** 2


def ease_in_out(t):
    return 3 * t * t - 2 * t * t * t


def mix(c1, c2, t):
    """两个 #rrggbb 之间线性插值。"""
    t = max(0.0, min(1.0, t))
    a = tuple(int(c1[i:i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(c2[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _arc_points(cx, cy, r, start_deg, end_deg, steps=7):
    import math
    pts = []
    for i in range(steps + 1):
        a = math.radians(start_deg + (end_deg - start_deg) * i / steps)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def rounded_points(x0, y0, x1, y1, r):
    """圆角矩形的平滑多边形顶点（扁平列表），既能画也能用 coords() 更新。"""
    r = min(r, (x1 - x0) / 2, (y1 - y0) / 2)
    pts = []
    pts += _arc_points(x1 - r, y0 + r, r, -90, 0)
    pts += _arc_points(x1 - r, y1 - r, r, 0, 90)
    pts += _arc_points(x0 + r, y1 - r, r, 90, 180)
    pts += _arc_points(x0 + r, y0 + r, r, 180, 270)
    return [c for p in pts for c in p]


def rounded(canvas, x0, y0, x1, y1, r, fill="", outline="", width=1, tags=None):
    kw = {"smooth": True, "splinesteps": 24}
    kw["fill"] = fill or ""
    kw["outline"] = outline or ""
    if outline:
        kw["width"] = width
    if tags:
        kw["tags"] = tags
    return canvas.create_polygon(rounded_points(x0, y0, x1, y1, r), **kw)
