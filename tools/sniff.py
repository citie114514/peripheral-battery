"""Passive HID input-report sniffer (read-only, overlapped, no writes).

Listens on every vendor-defined HID interface for N seconds and prints
whatever input reports arrive. Safe: opens with GENERIC_READ only.

Usage: python sniff.py [seconds] [vid:pid filter]
"""
import ctypes
import threading
import time
from ctypes import wintypes as w

import hid_probe as hp

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

GENERIC_READ = 0x80000000
FILE_SHARE_READ_WRITE = 0x3
OPEN_EXISTING = 3
FILE_FLAG_OVERLAPPED = 0x40000000
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 258
INFINITE = 0xFFFFFFFF


class OVERLAPPED(ctypes.Structure):
    _fields_ = [("Internal", ctypes.c_void_p),
                ("InternalHigh", ctypes.c_void_p),
                ("Offset", w.DWORD),
                ("OffsetHigh", w.DWORD),
                ("hEvent", w.HANDLE)]


kernel32.CreateEventW.restype = w.HANDLE
kernel32.CreateEventW.argtypes = [ctypes.c_void_p, w.BOOL, w.BOOL, w.LPCWSTR]
kernel32.ReadFile.argtypes = [w.HANDLE, ctypes.c_void_p, w.DWORD,
                              ctypes.POINTER(w.DWORD), ctypes.POINTER(OVERLAPPED)]
kernel32.GetOverlappedResult.argtypes = [w.HANDLE, ctypes.POINTER(OVERLAPPED),
                                         ctypes.POINTER(w.DWORD), w.BOOL]
kernel32.CancelIoEx.argtypes = [w.HANDLE, ctypes.POINTER(OVERLAPPED)]
kernel32.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
kernel32.ResetEvent.argtypes = [w.HANDLE]

stop = threading.Event()


def listen(rec, seconds):
    path = rec["path"]
    in_len = max(rec.get("in_len", 64), 8)
    h = kernel32.CreateFileW(path, GENERIC_READ, FILE_SHARE_READ_WRITE, None,
                             OPEN_EXISTING, FILE_FLAG_OVERLAPPED, None)
    if h in (None, -1, w.HANDLE(-1).value):
        print(f"  !! cannot open {rec.get('product')} err={ctypes.get_last_error()}")
        return
    tag = f"{rec.get('vid',0):04X}:{rec.get('pid',0):04X} up=0x{rec.get('usage_page',0):04X}"
    print(f"  listening {tag} in_len={in_len}")
    ev = kernel32.CreateEventW(None, True, False, None)
    buf = ctypes.create_string_buffer(in_len)
    deadline = time.time() + seconds
    found = {}
    try:
        while time.time() < deadline and not stop.is_set():
            ov = OVERLAPPED()
            ov.hEvent = ev
            nread = w.DWORD(0)
            kernel32.ResetEvent(ev)
            ok = kernel32.ReadFile(h, buf, in_len, ctypes.byref(nread), ctypes.byref(ov))
            if not ok:
                err = ctypes.get_last_error()
                if err != 997:  # ERROR_IO_PENDING
                    time.sleep(0.05)
                    continue
                r = kernel32.WaitForSingleObject(ev, 1500)
                if r != WAIT_OBJECT_0:
                    kernel32.CancelIoEx(h, ctypes.byref(ov))
                    kernel32.WaitForSingleObject(ev, 300)
                    continue
                if not kernel32.GetOverlappedResult(h, ctypes.byref(ov),
                                                    ctypes.byref(nread), False):
                    continue
            data = bytes(buf[:nread.value])
            # de-duplicate: only print when (len, first 4 bytes) not seen recently
            key = data[:4]
            now = time.time()
            if key in found and now - found[key] < 3:
                continue
            found[key] = now
            hexs = " ".join(f"{b:02X}" for b in data)
            print(f"  [{tag}] len={len(data)} {hexs}")
    finally:
        kernel32.CloseHandle(h)
        kernel32.CloseHandle(ev)


def main():
    seconds = float(__import__("sys").argv[1]) if len(__import__("sys").argv) > 1 else 8
    flt = __import__("sys").argv[2] if len(__import__("sys").argv) > 2 else None
    rows = hp.enumerate_hids()
    targets = [r for r in rows if r.get("usage_page", 0) >= 0xFF00]
    if flt:
        want = flt.lower()
        targets = [r for r in targets if f'{r.get("vid",0):04x}:{r.get("pid",0):04x}' == want]
    print(f"sniffing {len(targets)} vendor interfaces for {seconds}s "
          f"(move/click the device if nothing shows up)\n")
    threads = [threading.Thread(target=listen, args=(r, seconds), daemon=True)
               for r in targets]
    for t in threads:
        t.start()
    for t in threads:
        t.join(seconds + 5)
    print("\ndone")


if __name__ == "__main__":
    main()
