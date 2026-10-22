"""Dump HID report descriptors + value/button caps (report IDs, sizes) for a device."""
import ctypes
import sys
from ctypes import wintypes as w

import hid_probe as hp

hid = ctypes.WinDLL("hid", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)

HidP_Input, HidP_Output, HidP_Feature = 0, 1, 2
CTL_CODE = lambda dev, fn, method, access: (dev << 16) | (access << 14) | (fn << 2) | method
IOCTL_GET_REPORT_DESCRIPTOR = CTL_CODE(0x0B, 0, 3, 0)  # METHOD_NEITHER


class HIDP_VALUE_CAPS(ctypes.Structure):
    _fields_ = [
        ("UsagePage", w.USHORT), ("ReportID", ctypes.c_ubyte),
        ("IsAlias", ctypes.c_ubyte), ("BitField", w.USHORT),
        ("LinkCollection", w.USHORT), ("LinkUsage", w.USHORT),
        ("LinkUsagePage", w.USHORT), ("IsRange", w.USHORT),
        ("IsStringRange", w.USHORT), ("IsDesignatorRange", w.USHORT),
        ("IsAbsolute", w.USHORT), ("HasNull", ctypes.c_ubyte),
        ("Reserved", ctypes.c_ubyte), ("BitSize", w.USHORT),
        ("ReportCount", w.USHORT), ("Reserved2", w.USHORT * 5),
        ("UnitsExp", w.ULONG), ("Units", w.ULONG),
        ("LogicalMin", ctypes.c_long), ("LogicalMax", ctypes.c_long),
        ("PhysicalMin", ctypes.c_long), ("PhysicalMax", ctypes.c_long),
        ("UsageMin", w.USHORT), ("UsageMax", w.USHORT), ("StringMin", w.USHORT),
        ("StringMax", w.USHORT), ("DesignatorMin", w.USHORT),
        ("DesignatorMax", w.USHORT), ("DataIndexMin", w.USHORT),
        ("DataIndexMax", w.USHORT),
    ]


hid.HidP_GetValueCaps.argtypes = [ctypes.c_int, ctypes.POINTER(HIDP_VALUE_CAPS),
                                  ctypes.POINTER(w.USHORT), ctypes.c_void_p]
hid.HidD_GetPreparsedData.argtypes = [w.HANDLE, ctypes.POINTER(ctypes.c_void_p)]


def get_caps(pp, kind):
    n = w.USHORT(0)
    hid.HidP_GetValueCaps(kind, None, ctypes.byref(n), pp)
    if not n.value:
        return []
    arr = (HIDP_VALUE_CAPS * n.value)()
    hid.HidP_GetValueCaps(kind, arr, ctypes.byref(n), pp)
    out = []
    for c in arr[:n.value]:
        out.append(dict(page=c.UsagePage, report_id=c.ReportID, bits=c.BitSize,
                        count=c.ReportCount,
                        usages=f"0x{c.UsageMin:04X}-0x{c.UsageMax:04X}"))
    return out


def main():
    flt = (sys.argv[1] if len(sys.argv) > 1 else "362d:d028").lower()
    for rec in hp.enumerate_hids():
        if "%04x:%04x" % (rec.get("vid", 0), rec.get("pid", 0)) != flt:
            continue
        up = rec.get("usage_page")
        h = k32.CreateFileW(rec["path"], 0, 3, None, 3, 0, None)
        if h in (None, -1, w.HANDLE(-1).value):
            print(f"up=0x{up:04X}: open failed")
            continue
        try:
            pp = ctypes.c_void_p()
            if not hid.HidD_GetPreparsedData(h, ctypes.byref(pp)):
                print(f"up=0x{up:04X}: no preparsed data")
                continue
            print(f"\n=== up=0x{up:04X}  in={rec.get('in_len')} out={rec.get('out_len')} "
                  f"feat={rec.get('feat_len')}")
            for name, kind in (("output", HidP_Output), ("input", HidP_Input),
                               ("feature", HidP_Feature)):
                caps = get_caps(pp, kind)
                if caps:
                    print(f"  {name}:")
                    for c in caps:
                        print(f"    rid={c['report_id']:#04x} page=0x{c['page']:04X} "
                              f"bits={c['bits']} count={c['count']} usages={c['usages']}")
            hid.HidD_FreePreparsedData(pp)

            # raw report descriptor
            buf = ctypes.create_string_buffer(4096)
            nret = w.DWORD(0)
            ok = k32.DeviceIoControl(h, IOCTL_GET_REPORT_DESCRIPTOR,
                                     ctypes.byref(buf), 4096,
                                     ctypes.byref(buf), 4096,
                                     ctypes.byref(nret), None)
            if ok and nret.value:
                raw = bytes(buf[:nret.value])
                print("  descriptor:", " ".join(f"{b:02X}" for b in raw[:200]))
        finally:
            k32.CloseHandle(h)


if __name__ == "__main__":
    main()
