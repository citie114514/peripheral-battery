"""HID enumeration probe: lists every present HID interface with VID/PID,
product / manufacturer / serial strings and HID capabilities.

Pure stdlib + ctypes (no hidapi).
Run:  python hid_probe.py
"""
import ctypes
from ctypes import wintypes as w

# ---------- setupapi ----------
setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
hid = ctypes.WinDLL("hid", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

DIGCF_PRESENT = 0x02
DIGCF_DEVICEINTERFACE = 0x10
SPDRP_DEVICEDESC = 0x00
SPDRP_FRIENDLYNAME = 0x0C
SPDRP_LOCATION_INFORMATION = 0x0D
SPDRP_LOCATION_PATHS = 0x24
SPDRP_MFG = 0x0B


class GUID(ctypes.Structure):
    _fields_ = [("Data1", w.DWORD), ("Data2", w.WORD), ("Data3", w.WORD),
                ("Data4", ctypes.c_ubyte * 8)]


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [("cbSize", w.DWORD), ("InterfaceClassGuid", GUID),
                ("Flags", w.DWORD), ("Reserved", ctypes.POINTER(w.DWORD))]


class SP_DEVINFO_DATA(ctypes.Structure):
    _fields_ = [("cbSize", w.DWORD), ("ClassGuid", GUID),
                ("DevInst", w.DWORD), ("Reserved", ctypes.POINTER(w.DWORD))]


class SP_DEVICE_INTERFACE_DETAIL_DATA_W(ctypes.Structure):
    _fields_ = [("cbSize", w.DWORD), ("DevicePath", w.WCHAR * 1024)]


class HIDD_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Size", w.ULONG), ("VendorID", w.USHORT),
                ("ProductID", w.USHORT), ("VersionNumber", w.USHORT)]


class HIDP_CAPS(ctypes.Structure):
    _fields_ = [
        ("Usage", w.USHORT), ("UsagePage", w.USHORT),
        ("InputReportByteLength", w.USHORT), ("OutputReportByteLength", w.USHORT),
        ("FeatureReportByteLength", w.USHORT),
        ("Reserved", w.USHORT * 17),
        ("NumberLinkCollectionNodes", w.USHORT), ("NumberInputButtonCaps", w.USHORT),
        ("NumberInputValueCaps", w.USHORT), ("NumberInputDataIndices", w.USHORT),
        ("NumberOutputButtonCaps", w.USHORT), ("NumberOutputValueCaps", w.USHORT),
        ("NumberOutputDataIndices", w.USHORT), ("NumberFeatureButtonCaps", w.USHORT),
        ("NumberFeatureValueCaps", w.USHORT), ("NumberFeatureDataIndices", w.USHORT),
    ]


setupapi.SetupDiGetClassDevsW.restype = ctypes.c_void_p
setupapi.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(GUID), w.LPCWSTR,
                                         w.HWND, w.DWORD]
setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
    ctypes.c_void_p, ctypes.POINTER(SP_DEVINFO_DATA), ctypes.POINTER(GUID),
    w.DWORD, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA)]
setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
    ctypes.c_void_p, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA), ctypes.c_void_p,
    w.DWORD, ctypes.POINTER(w.DWORD), ctypes.POINTER(SP_DEVINFO_DATA)]
setupapi.SetupDiGetDeviceRegistryPropertyW.argtypes = [
    ctypes.c_void_p, ctypes.POINTER(SP_DEVINFO_DATA), w.DWORD,
    ctypes.POINTER(w.DWORD), ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD)]
setupapi.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]

hid.HidD_GetAttributes.argtypes = [w.HANDLE, ctypes.POINTER(HIDD_ATTRIBUTES)]
hid.HidD_GetProductString.argtypes = [w.HANDLE, ctypes.c_void_p, w.ULONG]
hid.HidD_GetManufacturerString.argtypes = [w.HANDLE, ctypes.c_void_p, w.ULONG]
hid.HidD_GetSerialNumberString.argtypes = [w.HANDLE, ctypes.c_void_p, w.ULONG]
hid.HidD_GetPreparsedData.argtypes = [w.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(HIDP_CAPS)]

kernel32.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p,
                                 w.DWORD, w.DWORD, w.HANDLE]
kernel32.CreateFileW.restype = w.HANDLE
kernel32.CloseHandle.argtypes = [w.HANDLE]


def guid_from_str(s):
    g = GUID()
    parts = s.split("-", 4)
    g.Data1 = int(parts[0], 16)
    g.Data2 = int(parts[1], 16)
    g.Data3 = int(parts[2], 16)
    tail = bytes.fromhex(parts[3] + parts[4])
    for i, b in enumerate(tail):
        g.Data4[i] = b
    return g


HID_GUID = guid_from_str("4d1e55b2-f16f-11cf-88cb-001111000030")


def hid_str(fn, h):
    buf = ctypes.create_unicode_buffer(256)
    if fn(h, buf, ctypes.sizeof(buf)):
        return buf.value
    return ""


def get_prop(dev_info, devinfo_data, prop):
    buf = ctypes.create_unicode_buffer(512)
    needed = w.DWORD(0)
    ok = setupapi.SetupDiGetDeviceRegistryPropertyW(
        dev_info, ctypes.byref(devinfo_data), prop, None,
        ctypes.cast(buf, ctypes.c_void_p), ctypes.sizeof(buf), ctypes.byref(needed))
    return buf.value if ok else ""


def open_path(path, access=0):
    """access=0 → metadata only (works for system-exclusive top-level collections)."""
    h = kernel32.CreateFileW(path, access, 3, None, 3, 0, None)
    if h == w.HANDLE(-1).value or h == -1:
        return None
    return h


def enumerate_hids():
    out = []
    dev_info = setupapi.SetupDiGetClassDevsW(
        ctypes.byref(HID_GUID), None, None,
        DIGCF_PRESENT | DIGCF_DEVICEINTERFACE)
    if dev_info == -1 or dev_info is None:
        return out
    did = SP_DEVINFO_DATA()
    did.cbSize = ctypes.sizeof(did)
    idx = 0
    while True:
        iface = SP_DEVICE_INTERFACE_DATA()
        iface.cbSize = ctypes.sizeof(iface)
        ok = setupapi.SetupDiEnumDeviceInterfaces(
            dev_info, None, ctypes.byref(HID_GUID), idx, ctypes.byref(iface))
        if not ok:
            break
        idx += 1
        req = w.DWORD(0)
        setupapi.SetupDiGetDeviceInterfaceDetailW(
            dev_info, ctypes.byref(iface), None, 0, ctypes.byref(req), None)
        if req.value == 0:
            continue
        buf = ctypes.create_string_buffer(req.value)
        detail = ctypes.cast(buf, ctypes.POINTER(SP_DEVICE_INTERFACE_DETAIL_DATA_W))
        # cbSize for the W variant is 8 on 64-bit (4 on 32-bit) per Win32 ABI
        detail.contents.cbSize = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
        did2 = SP_DEVINFO_DATA()
        did2.cbSize = ctypes.sizeof(did2)
        if not setupapi.SetupDiGetDeviceInterfaceDetailW(
                dev_info, ctypes.byref(iface), buf, req.value,
                ctypes.byref(req), ctypes.byref(did2)):
            continue
        path = ctypes.wstring_at(ctypes.addressof(buf) + 4)
        rec = {"path": path,
               "desc": get_prop(dev_info, did2, SPDRP_DEVICEDESC),
               "friendly": get_prop(dev_info, did2, SPDRP_FRIENDLYNAME),
               "mfg": get_prop(dev_info, did2, SPDRP_MFG),
               "location": get_prop(dev_info, did2, SPDRP_LOCATION_INFORMATION)}
        h = open_path(path, 0)
        if h:
            try:
                attrs = HIDD_ATTRIBUTES()
                attrs.Size = ctypes.sizeof(attrs)
                if hid.HidD_GetAttributes(h, ctypes.byref(attrs)):
                    rec["vid"] = attrs.VendorID
                    rec["pid"] = attrs.ProductID
                    rec["ver"] = attrs.VersionNumber
                rec["product"] = hid_str(hid.HidD_GetProductString, h)
                rec["manufacturer"] = hid_str(hid.HidD_GetManufacturerString, h)
                rec["serial"] = hid_str(hid.HidD_GetSerialNumberString, h)
                pp = ctypes.c_void_p()
                if hid.HidD_GetPreparsedData(h, ctypes.byref(pp)):
                    caps = HIDP_CAPS()
                    if hid.HidP_GetCaps(pp, ctypes.byref(caps)) == 0x00110000:  # HIDP_STATUS_SUCCESS
                        rec["usage_page"] = caps.UsagePage
                        rec["usage"] = caps.Usage
                        rec["in_len"] = caps.InputReportByteLength
                        rec["out_len"] = caps.OutputReportByteLength
                        rec["feat_len"] = caps.FeatureReportByteLength
                    hid.HidD_FreePreparsedData(pp)
            finally:
                kernel32.CloseHandle(h)
        out.append(rec)
    setupapi.SetupDiDestroyDeviceInfoList(dev_info)
    return out


if __name__ == "__main__":
    rows = enumerate_hids()
    print(f"{len(rows)} HID interfaces\n")
    for r in rows:
        print(f'{r.get("vid", 0):04X}:{r.get("pid", 0):04X}  '
              f'UP=0x{r.get("usage_page", 0):04X} U=0x{r.get("usage", 0):04X}  '
              f'in={r.get("in_len", 0)} out={r.get("out_len", 0)} feat={r.get("feat_len", 0)}')
        print(f'   product   : {r.get("product", "")!r}')
        print(f'   mfr       : {r.get("manufacturer", "")!r} / {r.get("mfg", "")!r}')
        print(f'   serial    : {r.get("serial", "")!r}')
        print(f'   desc      : {r.get("desc", "")!r} | {r.get("friendly", "")!r}')
        print(f'   location  : {r.get("location", "")!r}')
        print(f'   path      : {r["path"]}')
        print()
