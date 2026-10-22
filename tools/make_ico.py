"""把 battery 图标渲染成多尺寸 .ico（纯 stdlib + GDI，不需要 Pillow）。"""
import ctypes
import struct
import sys

from icons import _downsample, _draw, SUPERSAMPLE

SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]


def render(size, percent=100):
    big = size * SUPERSAMPLE
    dc, hbmp, bits = _draw(big, percent, False)
    src = ctypes.string_at(bits, big * big * 4)
    alpha = bytearray(len(src))
    for i in range(0, len(src), 4):
        v = max(src[i], src[i + 1], src[i + 2])
        alpha[i] = alpha[i + 1] = alpha[i + 2] = v
        alpha[i + 3] = v
    pixels = _downsample(bytes(alpha), big, size)
    # 上色为深墨色（浅色任务栏下也看得清），exe 图标用暖橙
    r, g, b = 0xC2, 0x59, 0x3C
    out = bytearray(pixels)
    for i in range(0, len(out), 4):
        a = out[i + 3]
        out[i] = b * a // 255
        out[i + 1] = g * a // 255
        out[i + 2] = r * a // 255
    # GDI 画的 + alpha 是 top-down BGRA；ICO 要 bottom-up
    rows = [bytes(out[y * size * 4:(y + 1) * size * 4]) for y in range(size)]
    return b"".join(reversed(rows))


def main(path):
    entries, blobs = [], []
    offset = 6 + 16 * len(SIZES)
    for size in SIZES:
        pixels = render(size)
        mask_row = ((size + 31) // 32) * 4
        mask = b"\x00" * (mask_row * size)
        header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0,
                             len(pixels) + len(mask), 0, 0, 0, 0)
        blob = header + pixels + mask
        entries.append(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32,
                                   len(blob), offset))
        blobs.append(blob)
        offset += len(blob)
    with open(path, "wb") as f:
        f.write(struct.pack("<HHH", 0, 1, len(SIZES)))
        for e in entries:
            f.write(e)
        for b in blobs:
            f.write(b)
    print("wrote", path)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "app.ico")
