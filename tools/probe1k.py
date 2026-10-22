"""Probe the 'Ultra-Link 8K' receiver with the launcher's 1k-bridge protocol.

Sends  0xBC (startNotify) as a 32-byte report, then listens for
0xE2 (monitor-base) replies. All I/O is OVERLAPPED so nothing can hang.

Usage: python probe1k.py [vid:pid]
"""
import ctypes
import sys
import time
from ctypes import wintypes as w

import hid_probe as hp

k32 = ctypes.WinDLL("kernel32", use_last_error=True)

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_RW = 0x3
OPEN_EXISTING = 3
FILE_FLAG_OVERLAPPED = 0x40000000
WAIT_OBJECT_0 = 0
ERROR_IO_PENDING = 997


class OVERLAPPED(ctypes.Structure):
    _fields_ = [("Internal", ctypes.c_void_p), ("InternalHigh", ctypes.c_void_p),
                ("Offset", w.DWORD), ("OffsetHigh", w.DWORD), ("hEvent", w.HANDLE)]


k32.CreateEventW.restype = w.HANDLE
k32.CreateEventW.argtypes = [ctypes.c_void_p, w.BOOL, w.BOOL, w.LPCWSTR]
k32.ReadFile.argtypes = [w.HANDLE, ctypes.c_void_p, w.DWORD,
                         ctypes.POINTER(w.DWORD), ctypes.POINTER(OVERLAPPED)]
k32.WriteFile.argtypes = [w.HANDLE, ctypes.c_void_p, w.DWORD,
                          ctypes.POINTER(w.DWORD), ctypes.POINTER(OVERLAPPED)]
k32.GetOverlappedResult.argtypes = [w.HANDLE, ctypes.POINTER(OVERLAPPED),
                                    ctypes.POINTER(w.DWORD), w.BOOL]
k32.CancelIoEx.argtypes = [w.HANDLE, ctypes.POINTER(OVERLAPPED)]
k32.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
k32.ResetEvent.argtypes = [w.HANDLE]
k32.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p,
                            w.DWORD, w.DWORD, w.HANDLE]
k32.CreateFileW.restype = w.HANDLE


def hexs(data):
    return " ".join(f"{b:02X}" for b in data)


class Chan:
    def __init__(self, path, out_len, in_len):
        self.h = k32.CreateFileW(path, GENERIC_READ | GENERIC_WRITE, FILE_SHARE_RW,
                                 None, OPEN_EXISTING, FILE_FLAG_OVERLAPPED, None)
        self.ok = self.h not in (None, -1, w.HANDLE(-1).value)
        self.out_len = out_len
        self.in_len = in_len
        self.ev = k32.CreateEventW(None, True, False, None) if self.ok else None

    def write(self, payload):
        if not self.ok:
            return False
        buf = ctypes.create_string_buffer(bytes(payload), self.out_len)
        ov = OVERLAPPED()
        ov.hEvent = self.ev
        n = w.DWORD(0)
        k32.ResetEvent(self.ev)
        r = k32.WriteFile(self.h, buf, self.out_len, ctypes.byref(n), ctypes.byref(ov))
        if not r:
            if ctypes.get_last_error() != ERROR_IO_PENDING:
                return False
            if k32.WaitForSingleObject(self.ev, 1000) != WAIT_OBJECT_0:
                k32.CancelIoEx(self.h, ctypes.byref(ov))
                return False
            if not k32.GetOverlappedResult(self.h, ctypes.byref(ov), ctypes.byref(n), False):
                return False
        return True

    def read(self, timeout_ms):
        if not self.ok:
            return None
        buf = ctypes.create_string_buffer(self.in_len)
        ov = OVERLAPPED()
        ov.hEvent = self.ev
        n = w.DWORD(0)
        k32.ResetEvent(self.ev)
        r = k32.ReadFile(self.h, buf, self.in_len, ctypes.byref(n), ctypes.byref(ov))
        if not r:
            if ctypes.get_last_error() != ERROR_IO_PENDING:
                return None
            if k32.WaitForSingleObject(self.ev, timeout_ms) != WAIT_OBJECT_0:
                k32.CancelIoEx(self.h, ctypes.byref(ov))
                k32.WaitForSingleObject(self.ev, 200)
                return None
            if not k32.GetOverlappedResult(self.h, ctypes.byref(ov), ctypes.byref(n), False):
                return None
        return bytes(buf[:n.value])

    def close(self):
        if self.ok:
            k32.CloseHandle(self.h)
            k32.CloseHandle(self.ev)


def main():
    flt = sys.argv[1].lower() if len(sys.argv) > 1 else "362d:d028"
    rows = [r for r in hp.enumerate_hids()
            if f'{r.get("vid",0):04x}:{r.get("pid",0):04x}' == flt
            and r.get("usage_page", 0) in (0x8C, 0xFFC1, 0xFF60)]

    for rec in rows:
        up = rec.get("usage_page")
        print(f"\n=== {flt} up=0x{up:04X} in={rec.get('in_len')} out={rec.get('out_len')}")
        ch = Chan(rec["path"], max(rec.get("out_len", 64), 8), max(rec.get("in_len", 64), 8))
        if not ch.ok:
            print("  cannot open (err=%d)" % ctypes.get_last_error())
            continue
        try:
            # 1) launcher-style startNotify: 0xBC in the first byte
            starts = []
            for cmd in (0xBC, 0xE1, 0xE2):
                payload = bytearray(32)
                payload[0] = cmd
                starts.append((cmd, ch.write(payload)))
            print("  writes:", ", ".join(f"{c:02X}={ok}" for c, ok in starts))
            # 2) listen
            deadline = time.time() + 6
            seen = 0
            while time.time() < deadline:
                data = ch.read(900)
                if not data:
                    continue
                seen += 1
                print(f"  RECV len={len(data)} {hexs(data)}")
                if data[0] == 0xE2:
                    print(f"  >>> monitor-base: workMode={data[1]} connect={data[2]} "
                          f"powerState={data[3]} power={data[4]} dpi={data[5]} poll={data[6]}")
                if seen > 40:
                    break
            if not seen:
                print("  (no input reports)")
        finally:
            ch.close()


if __name__ == "__main__":
    main()
