"""极简 HID 层：纯 ctypes 调用 setupapi / hid / kernel32。

设计要点（踩过的坑都在这）：
* 所有读写都用 FILE_FLAG_OVERLAPPED + 事件超时，绝不在同一句柄上做
  "阻塞 ReadFile + 并发 WriteFile"，那会把进程直接打死。
* 只能用 dwDesiredAccess=0 打开的顶层集合（鼠标/键盘/笔），这里不去碰。
* read() 返回的是 ReadFile 拿到的原始缓冲区：带 report id 的接口
  首字节就是 report id，协议层自己按需切。
"""
import ctypes
import threading
import time
from ctypes import wintypes as w

setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
hid = ctypes.WinDLL("hid", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)

DIGCF_PRESENT = 0x02
DIGCF_DEVICEINTERFACE = 0x10
SPDRP_DEVICEDESC = 0x00
SPDRP_FRIENDLYNAME = 0x0C

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_RW = 0x3
OPEN_EXISTING = 3
FILE_FLAG_OVERLAPPED = 0x40000000
ERROR_IO_PENDING = 997
WAIT_OBJECT_0 = 0
INVALID_HANDLE = ctypes.c_void_p(-1).value


class GUID(ctypes.Structure):
    _fields_ = [("Data1", w.DWORD), ("Data2", w.WORD), ("Data3", w.WORD),
                ("Data4", ctypes.c_ubyte * 8)]


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [("cbSize", w.DWORD), ("InterfaceClassGuid", GUID),
                ("Flags", w.DWORD), ("Reserved", ctypes.c_void_p)]


class SP_DEVINFO_DATA(ctypes.Structure):
    _fields_ = [("cbSize", w.DWORD), ("ClassGuid", GUID),
                ("DevInst", w.DWORD), ("Reserved", ctypes.c_void_p)]


class SP_DEVICE_INTERFACE_DETAIL_DATA_W(ctypes.Structure):
    _fields_ = [("cbSize", w.DWORD), ("DevicePath", w.WCHAR * 1024)]


class HIDD_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Size", w.ULONG), ("VendorID", w.USHORT),
                ("ProductID", w.USHORT), ("VersionNumber", w.USHORT)]


class HIDP_CAPS(ctypes.Structure):
    _fields_ = [
        ("Usage", w.USHORT), ("UsagePage", w.USHORT),
        ("InputReportByteLength", w.USHORT), ("OutputReportByteLength", w.USHORT),
        ("FeatureReportByteLength", w.USHORT), ("Reserved", w.USHORT * 17),
        ("NumberLinkCollectionNodes", w.USHORT), ("NumberInputButtonCaps", w.USHORT),
        ("NumberInputValueCaps", w.USHORT), ("NumberInputDataIndices", w.USHORT),
        ("NumberOutputButtonCaps", w.USHORT), ("NumberOutputValueCaps", w.USHORT),
        ("NumberOutputDataIndices", w.USHORT), ("NumberFeatureButtonCaps", w.USHORT),
        ("NumberFeatureValueCaps", w.USHORT), ("NumberFeatureDataIndices", w.USHORT),
    ]


class OVERLAPPED(ctypes.Structure):
    _fields_ = [("Internal", ctypes.c_void_p), ("InternalHigh", ctypes.c_void_p),
                ("Offset", w.DWORD), ("OffsetHigh", w.DWORD), ("hEvent", w.HANDLE)]


setupapi.SetupDiGetClassDevsW.restype = ctypes.c_void_p
setupapi.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(GUID), w.LPCWSTR, w.HWND, w.DWORD]
setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
    ctypes.c_void_p, ctypes.POINTER(SP_DEVINFO_DATA), ctypes.POINTER(GUID),
    w.DWORD, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA)]
setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
    ctypes.c_void_p, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA), ctypes.c_void_p,
    w.DWORD, ctypes.POINTER(w.DWORD), ctypes.POINTER(SP_DEVINFO_DATA)]
setupapi.SetupDiGetDeviceRegistryPropertyW.argtypes = [
    ctypes.c_void_p, ctypes.POINTER(SP_DEVINFO_DATA), w.DWORD, ctypes.POINTER(w.DWORD),
    ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD)]
setupapi.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]

hid.HidD_GetAttributes.argtypes = [w.HANDLE, ctypes.POINTER(HIDD_ATTRIBUTES)]
hid.HidD_GetProductString.argtypes = [w.HANDLE, ctypes.c_void_p, w.ULONG]
hid.HidD_GetManufacturerString.argtypes = [w.HANDLE, ctypes.c_void_p, w.ULONG]
hid.HidD_GetSerialNumberString.argtypes = [w.HANDLE, ctypes.c_void_p, w.ULONG]
hid.HidD_GetPreparsedData.argtypes = [w.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(HIDP_CAPS)]

k32.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p,
                            w.DWORD, w.DWORD, w.HANDLE]
k32.CreateFileW.restype = w.HANDLE
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
k32.CloseHandle.argtypes = [w.HANDLE]


def _guid_from_str(s):
    g = GUID()
    a, b, c, d, e = s.split("-", 4)
    g.Data1, g.Data2, g.Data3 = int(a, 16), int(b, 16), int(c, 16)
    tail = bytes.fromhex(d + e)
    for i, byte in enumerate(tail):
        g.Data4[i] = byte
    return g


HID_GUID = _guid_from_str("4d1e55b2-f16f-11cf-88cb-001111000030")


class HidInterface:
    """一个 HID 接口（一个设备路径）。"""

    __slots__ = ("path", "desc", "vid", "pid", "version", "product",
                 "manufacturer", "serial", "usage_page", "usage",
                 "in_len", "out_len", "feat_len")

    def __init__(self, **kw):
        for key in self.__slots__:
            setattr(self, key, kw.get(key))

    def __repr__(self):
        return (f"<HidInterface {self.vid:04X}:{self.pid:04X} "
                f"up=0x{self.usage_page:04X} {self.product!r}>")

    @property
    def key(self):
        return f"{self.vid:04X}:{self.pid:04X}"

    def open(self, read=True, write=True):
        return HidHandle(self, read, write)


class HidHandle:
    """重叠 I/O 句柄封装。"""

    def __init__(self, iface, read=True, write=True):
        access = (GENERIC_READ if read else 0) | (GENERIC_WRITE if write else 0)
        self.iface = iface
        self.in_len = max(iface.in_len or 64, 1)
        self.out_len = max(iface.out_len or 64, 1)
        self.h = k32.CreateFileW(iface.path, access, FILE_SHARE_RW, None,
                                 OPEN_EXISTING, FILE_FLAG_OVERLAPPED, None)
        self.ok = self.h not in (None, INVALID_HANDLE)
        self.ev = k32.CreateEventW(None, True, False, None) if self.ok else None
        self._lock = threading.Lock()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def write(self, payload, report_id=None, timeout_ms=800):
        """payload 不含 report id；report_id 为 None 时按接口约定补齐/不补。

        对声明了 report id 的接口，Windows 要求缓冲区首字节就是 report id。
        """
        if not self.ok:
            return False
        with self._lock:
            buf = bytearray(payload)
            if report_id is not None:
                buf = bytearray([report_id]) + buf
            buf = bytes(buf[: self.out_len]).ljust(self.out_len, b"\x00")
            data = ctypes.create_string_buffer(buf, len(buf))
            ov = OVERLAPPED()
            ov.hEvent = self.ev
            n = w.DWORD(0)
            k32.ResetEvent(self.ev)
            r = k32.WriteFile(self.h, data, len(buf), ctypes.byref(n), ctypes.byref(ov))
            if not r:
                if ctypes.get_last_error() != ERROR_IO_PENDING:
                    return False
                if k32.WaitForSingleObject(self.ev, timeout_ms) != WAIT_OBJECT_0:
                    k32.CancelIoEx(self.h, ctypes.byref(ov))
                    return False
                if not k32.GetOverlappedResult(self.h, ctypes.byref(ov), ctypes.byref(n), False):
                    return False
            return True

    def write_raw(self, buf, timeout_ms=800):
        """原样写入（长度按 out_len 截断/补零，调用者自己管 report id）。"""
        if not self.ok:
            return False
        return self.write(bytes(buf), report_id=None, timeout_ms=timeout_ms)

    def read(self, timeout_ms=500):
        """读一条输入报告；超时返回 None。"""
        if not self.ok:
            return None
        with self._lock:
            data = ctypes.create_string_buffer(self.in_len)
            ov = OVERLAPPED()
            ov.hEvent = self.ev
            n = w.DWORD(0)
            k32.ResetEvent(self.ev)
            r = k32.ReadFile(self.h, data, self.in_len, ctypes.byref(n), ctypes.byref(ov))
            if not r:
                if ctypes.get_last_error() != ERROR_IO_PENDING:
                    return None
                if k32.WaitForSingleObject(self.ev, timeout_ms) != WAIT_OBJECT_0:
                    k32.CancelIoEx(self.h, ctypes.byref(ov))
                    k32.WaitForSingleObject(self.ev, 150)
                    return None
                if not k32.GetOverlappedResult(self.h, ctypes.byref(ov), ctypes.byref(n), False):
                    return None
            return bytes(data[: n.value])

    def drain(self):
        """丢掉缓冲里积压的报告。"""
        for _ in range(24):
            if self.read(20) is None:
                return

    def close(self):
        if self.ok:
            k32.CancelIoEx(self.h, None)
            k32.CloseHandle(self.h)
            self.ok = False
        if self.ev:
            k32.CloseHandle(self.ev)
            self.ev = None


def _get_prop(dev_info, devinfo_data, prop):
    buf = ctypes.create_unicode_buffer(512)
    needed = w.DWORD(0)
    ok = setupapi.SetupDiGetDeviceRegistryPropertyW(
        dev_info, ctypes.byref(devinfo_data), prop, None,
        ctypes.cast(buf, ctypes.c_void_p), ctypes.sizeof(buf), ctypes.byref(needed))
    return buf.value if ok else ""


def _hid_string(fn, handle):
    buf = ctypes.create_unicode_buffer(256)
    return buf.value if fn(handle, buf, ctypes.sizeof(buf)) else ""


def enumerate_interfaces():
    """枚举当前所有 HID 接口。"""
    out = []
    dev_info = setupapi.SetupDiGetClassDevsW(
        ctypes.byref(HID_GUID), None, None, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE)
    if dev_info in (None, INVALID_HANDLE):
        return out
    did = SP_DEVINFO_DATA()
    did.cbSize = ctypes.sizeof(did)
    idx = 0
    try:
        while True:
            iface = SP_DEVICE_INTERFACE_DATA()
            iface.cbSize = ctypes.sizeof(iface)
            if not setupapi.SetupDiEnumDeviceInterfaces(
                    dev_info, None, ctypes.byref(HID_GUID), idx, ctypes.byref(iface)):
                break
            idx += 1
            need = w.DWORD(0)
            setupapi.SetupDiGetDeviceInterfaceDetailW(
                dev_info, ctypes.byref(iface), None, 0, ctypes.byref(need), None)
            if not need.value:
                continue
            raw = ctypes.create_string_buffer(need.value)
            detail = ctypes.cast(raw, ctypes.POINTER(SP_DEVICE_INTERFACE_DETAIL_DATA_W))
            detail.contents.cbSize = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
            did2 = SP_DEVINFO_DATA()
            did2.cbSize = ctypes.sizeof(did2)
            if not setupapi.SetupDiGetDeviceInterfaceDetailW(
                    dev_info, ctypes.byref(iface), raw, need.value,
                    ctypes.byref(need), ctypes.byref(did2)):
                continue
            path = ctypes.wstring_at(ctypes.addressof(raw) + 4)
            rec = HidInterface(path=path,
                               desc=_get_prop(dev_info, did2, SPDRP_DEVICEDESC))
            h = k32.CreateFileW(path, 0, FILE_SHARE_RW, None, OPEN_EXISTING, 0, None)
            if h in (None, INVALID_HANDLE):
                continue
            try:
                attrs = HIDD_ATTRIBUTES()
                attrs.Size = ctypes.sizeof(attrs)
                if hid.HidD_GetAttributes(h, ctypes.byref(attrs)):
                    rec.vid = attrs.VendorID
                    rec.pid = attrs.ProductID
                    rec.version = attrs.VersionNumber
                rec.product = _hid_string(hid.HidD_GetProductString, h)
                rec.manufacturer = _hid_string(hid.HidD_GetManufacturerString, h)
                rec.serial = _hid_string(hid.HidD_GetSerialNumberString, h)
                pp = ctypes.c_void_p()
                if hid.HidD_GetPreparsedData(h, ctypes.byref(pp)):
                    caps = HIDP_CAPS()
                    if hid.HidP_GetCaps(pp, ctypes.byref(caps)) == 0x00110000:
                        rec.usage_page = caps.UsagePage
                        rec.usage = caps.Usage
                        rec.in_len = caps.InputReportByteLength
                        rec.out_len = caps.OutputReportByteLength
                        rec.feat_len = caps.FeatureReportByteLength
                    hid.HidD_FreePreparsedData(pp)
            finally:
                k32.CloseHandle(h)
            if rec.vid is not None:
                out.append(rec)
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(dev_info)
    return out


def find_interface(interfaces, vid, pid, usage_page=None):
    for rec in interfaces:
        if rec.vid == vid and rec.pid == pid:
            if usage_page is None or rec.usage_page == usage_page:
                return rec
    return None
