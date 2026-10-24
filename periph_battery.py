"""外设电量（贱驴 RSR5S 鼠标 + PMO P75 键盘）后台部分。

* 电量读取：hidlib（ctypes HID）+ protocols（两个厂商协议）
* 托盘：ctypes 手写 Shell_NotifyIcon，系统电池图标同款单色字形
* 界面：webapp.py（WebView2 + HTML/CSS，见 ui/index.html）
* 用法：
    python periph_battery.py            常驻（托盘 + 窗口）
    python periph_battery.py --once     打印一次电量后退出
    python periph_battery.py --panel    只开窗口
    python periph_battery.py --install  建桌面快捷方式
    python periph_battery.py --autostart on|off
"""
import argparse
import ctypes
import json
import os
import queue
import sys
import threading
import time
import traceback
from ctypes import wintypes as w

import hidlib
import protocols
import ui_theme as T
from icons import make_battery_icon, user32, gdi32

APP_NAME = "外设电量"
CLASS_NAME = "PeripheralBatteryTrayWnd"
MUTEX_NAME = "Local\\PeripheralBatteryTrayMutex"
CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                          "PeripheralBattery")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
DEFAULT_CONFIG = {"interval": 60, "tray": True}

INTERVALS = [("30 秒", 30), ("1 分钟", 60), ("2 分钟", 120),
             ("5 分钟", 300), ("10 分钟", 600), ("30 分钟", 1800)]

WM_DESTROY = 0x0002
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
setupapi = ctypes.WinDLL("setupapi", use_last_error=True)

user32.DefWindowProcW.restype = ctypes.c_void_p
user32.DefWindowProcW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
user32.CreateWindowExW.restype = w.HWND
user32.CreateWindowExW.argtypes = [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   w.HWND, w.HMENU, w.HINSTANCE, ctypes.c_void_p]
user32.RegisterClassW.argtypes = [ctypes.c_void_p]
user32.DefWindowProcW.restype = ctypes.c_longlong
user32.GetMessageW.argtypes = [ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(w.MSG)]
user32.TranslateMessage.argtypes = [ctypes.POINTER(w.MSG)]
user32.SetTimer.argtypes = [w.HWND, w.UINT, w.UINT, ctypes.c_void_p]
user32.KillTimer.argtypes = [w.HWND, w.UINT]
user32.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.FindWindowW.restype = w.HWND
user32.FindWindowW.argtypes = [w.LPCWSTR, w.LPCWSTR]
user32.DestroyWindow.argtypes = [w.HWND]
user32.SendMessageW.restype = ctypes.c_longlong
user32.SendMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
user32.SetForegroundWindow.argtypes = [w.HWND]

user32.CreatePopupMenu.restype = w.HMENU
user32.AppendMenuW.argtypes = [w.HMENU, w.UINT, ctypes.c_size_t, w.LPCWSTR]
user32.TrackPopupMenu.restype = ctypes.c_int
user32.TrackPopupMenu.argtypes = [w.HMENU, w.UINT, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, w.HWND, ctypes.c_void_p]
user32.DestroyMenu.argtypes = [w.HMENU]
user32.GetCursorPos.argtypes = [ctypes.c_void_p]
user32.SetWindowPos.argtypes = [w.HWND, w.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, w.UINT]
user32.GetWindowRect.argtypes = [w.HWND, ctypes.c_void_p]

shell32.Shell_NotifyIconW.argtypes = [w.DWORD, ctypes.c_void_p]

kernel32.GetModuleHandleW.restype = w.HMODULE
kernel32.GetModuleHandleW.argtypes = [w.LPCWSTR]
kernel32.CreateMutexW.restype = w.HANDLE
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, w.BOOL, w.LPCWSTR]
user32.LoadIconW.restype = w.HICON
user32.LoadIconW.argtypes = [w.HINSTANCE, ctypes.c_void_p]
user32.DestroyIcon.argtypes = [w.HICON]

WM_TIMER = 0x0113
WM_COMMAND = 0x0111
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_APP = 0x8000
WM_TRAY_CALLBACK = WM_APP + 2
WM_SHOW_PANEL = WM_APP + 1
WM_REFRESH_ICONS = WM_APP + 3

MF_STRING = 0x0000
MF_SEPARATOR = 0x0800
MF_CHECKED = 0x0008
TPM_LEFTALIGN = 0x0000
TPM_BOTTOMALIGN = 0x0020
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100
TPM_NONOTIFY = 0x0080

ID_OPEN, ID_REFRESH, ID_AUTOSTART, ID_QUIT = 1, 2, 3, 4

NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP = 0x1, 0x2, 0x4
IDI_APPLICATION = 32512

user32.RegisterWindowMessageW.restype = w.UINT
user32.RegisterWindowMessageW.argtypes = [w.LPCWSTR]
# Explorer 重启 / 通知区重建时广播的消息，收到就必须重新挂图标
TASKBAR_CREATED = user32.RegisterWindowMessageW("TaskbarCreated")

TIMER_RETRY = 2          # 图标没挂上时的快速重试定时器 id
ICON_TTL = 12.0          # 旧 HICON 延迟回收，Explorer 可能还在引用


class GUID(ctypes.Structure):
    _fields_ = [("Data1", w.DWORD), ("Data2", w.WORD), ("Data3", w.WORD),
                ("Data4", ctypes.c_ubyte * 8)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", w.DWORD), ("hWnd", w.HWND), ("uID", w.UINT),
                ("uFlags", w.UINT), ("uCallbackMessage", w.UINT), ("hIcon", w.HICON),
                ("szTip", w.WCHAR * 128), ("dwState", w.DWORD), ("dwStateMask", w.DWORD),
                ("szInfo", w.WCHAR * 256), ("uVersion", w.UINT),
                ("szInfoTitle", w.WCHAR * 64), ("dwInfoFlags", w.DWORD),
                ("guidItem", GUID), ("hBalloonIcon", w.HICON)]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", w.UINT), ("lpfnWndProc", ctypes.c_void_p),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", w.HINSTANCE), ("hIcon", w.HICON), ("hCursor", w.HANDLE),
                ("hbrBackground", w.HANDLE), ("lpszMenuName", w.LPCWSTR),
                ("lpszClassName", w.LPCWSTR)]


WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, w.HWND, w.UINT, w.WPARAM, w.LPARAM)


# ----------------------------------------------------------------- 配置
def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    return cfg


def save_config(cfg):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ----------------------------------------------------------------- 开机自启
def _com_method(ptr, index, argtypes):
    vtbl = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    proto = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)
    return proto(vtbl[index])


def startup_lnk_path():
    folder = os.path.join(os.environ["APPDATA"], "Microsoft", "Windows",
                          "Start Menu", "Programs", "Startup")
    return os.path.join(folder, f"{APP_NAME}.lnk")


def desktop_dir():
    """从注册表拿真实桌面目录（兼容 OneDrive 重定向）。"""
    import winreg
    candidates = []
    for path in (r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
                 r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
                value = winreg.QueryValueEx(key, "Desktop")[0]
                candidates.append(os.path.expandvars(value))
        except OSError:
            pass
    candidates.append(os.path.join(os.environ.get("USERPROFILE", "~"), "Desktop"))
    for path in candidates:
        if path and os.path.isdir(path):
            return path
    return candidates[0]


def desktop_lnk_path():
    return os.path.join(desktop_dir(), f"{APP_NAME}.lnk")


def autostart_enabled():
    return os.path.exists(startup_lnk_path())


def set_autostart(enable):
    lnk = startup_lnk_path()
    if not enable:
        try:
            os.remove(lnk)
        except FileNotFoundError:
            pass
        return True
    return write_shortcut(lnk)


def write_shortcut(lnk):
    """用纯 ctypes 写 .lnk（打包后指向 exe，源码模式指向 pythonw + 脚本）。"""
    frozen = getattr(sys, "frozen", False)
    if frozen:
        exe = sys.executable
        arguments = ""
        workdir = os.path.dirname(exe)
    else:
        exe = os.path.join(sys.prefix, "pythonw.exe")
        if not os.path.exists(exe):
            exe = sys.executable
            if exe.lower().endswith("python.exe"):
                candidate = exe[:-len("python.exe")] + "pythonw.exe"
                if os.path.exists(candidate):
                    exe = candidate
        script = os.path.abspath(__file__)
        arguments = f'"{script}"'
        workdir = os.path.dirname(script)
    clsid = GUID()
    ctypes.windll.ole32.CLSIDFromString(
        ctypes.c_wchar_p("{00021401-0000-0000-C000-000000000046}"), ctypes.byref(clsid))
    iid = GUID()
    ctypes.windll.ole32.CLSIDFromString(
        ctypes.c_wchar_p("{000214F9-0000-0000-C000-000000000046}"), ctypes.byref(iid))
    shell_link = ctypes.c_void_p()
    hr = ctypes.windll.ole32.CoCreateInstance(
        ctypes.byref(clsid), None, 1, ctypes.byref(iid), ctypes.byref(shell_link))
    if hr != 0 or not shell_link:
        return False
    try:
        VP = ctypes.c_void_p
        _com_method(shell_link, 20, [ctypes.c_wchar_p])(shell_link, ctypes.c_wchar_p(exe))
        _com_method(shell_link, 11, [ctypes.c_wchar_p])(shell_link, ctypes.c_wchar_p(arguments))
        _com_method(shell_link, 9, [ctypes.c_wchar_p])(
            shell_link, ctypes.c_wchar_p(workdir))
        _com_method(shell_link, 7, [ctypes.c_wchar_p])(shell_link, ctypes.c_wchar_p(APP_NAME))
        _com_method(shell_link, 17, [ctypes.c_wchar_p, ctypes.c_int])(
            shell_link, ctypes.c_wchar_p(exe), 0)
        persist = VP()
        iid_pf = GUID()
        ctypes.windll.ole32.CLSIDFromString(
            ctypes.c_wchar_p("{0000010B-0000-0000-C000-000000000046}"), ctypes.byref(iid_pf))
        _com_method(shell_link, 0, [ctypes.POINTER(GUID), ctypes.POINTER(VP)])(
            shell_link, ctypes.byref(iid_pf), ctypes.byref(persist))
        if not persist:
            return False
        try:
            hr = _com_method(persist, 6, [ctypes.c_wchar_p, ctypes.c_int])(
                persist, ctypes.c_wchar_p(lnk), 1)
            return hr == 0
        finally:
            _com_method(persist, 2, [])(persist)
    finally:
        _com_method(shell_link, 2, [])(shell_link)


# ----------------------------------------------------------------- 托盘
class Tray(threading.Thread):
    """托盘线程。

    「图标偶尔消失」的三种成因和对应处理：
    1. Explorer 重启 / 通知区重建（主题切换、资源管理器崩溃、Win+Q 刷新）
       → 监听 TaskbarCreated 广播消息，收到就全部重新 NIM_ADD。
    2. 开机自启时我们比 Explorer 的通知区更早起来，NIM_ADD 会直接失败
       → 起一个 2 秒的快速重试定时器，挂上为止。
    3. NIM_MODIFY 返回成功但其实图标早没了（通知区里已经没我们）
       → 每次刷新都校验，MODIFY 失败就退回 ADD。
    另外：旧 HICON 不立刻 DestroyIcon（Explorer 可能还在引用），延迟回收。
    """

    def __init__(self, runtime):
        super().__init__(daemon=True)
        self.runtime = runtime
        self.hwnd = None
        self.icons = {}
        self._graveyard = []          # [(可销毁时间, HICON)]
        self._added = set()           # 确认在通知区里的 uid
        self._proc = WNDPROC(self._wndproc)
        self.ready = threading.Event()

    # ------------------------------------------------ 窗口过程
    def _wndproc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_TRAY_CALLBACK:
                event = int(lparam) & 0xFFFF
                if event == WM_RBUTTONUP:
                    self._popup_menu()
                elif event == WM_LBUTTONUP:
                    self.runtime.request_panel()
                return 0
            if msg == WM_TIMER:
                if int(wparam) == TIMER_RETRY:
                    self._ensure_icons()
                else:
                    self.runtime.request_refresh("定时刷新")
                return 0
            if msg == WM_SHOW_PANEL:
                self.runtime.request_panel()
                return 0
            if msg == WM_REFRESH_ICONS:
                self._apply_icons()
                return 0
            if TASKBAR_CREATED and msg == TASKBAR_CREATED:
                self.runtime.note("通知区被重建，重新挂图标")
                self._added.clear()
                self._ensure_icons()
                return 0
            if msg == WM_DESTROY:
                for uid in list(self.icons):
                    self._notify(NIM_DELETE, uid)
                for _when, handle in self._graveyard:
                    user32.DestroyIcon(handle)
                self._graveyard.clear()
                user32.PostQuitMessage(0)   # 关键：否则进程变僵尸还占着单实例锁
                return 0
        except Exception:
            if self.runtime.debug:
                traceback.print_exc()
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    # ------------------------------------------------ Shell_NotifyIcon
    def _notify(self, action, uid, tip=None):
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = uid
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAY_CALLBACK
        nid.hIcon = self.icons.get(uid, 0) or user32.LoadIconW(None, IDI_APPLICATION)
        nid.szTip = (tip or APP_NAME)[:127]
        return bool(shell32.Shell_NotifyIconW(action, ctypes.byref(nid)))

    def _ensure_icons(self):
        """补挂缺失的图标。

        注意 NIM_ADD 在「图标已存在」时也会返回 False，所以 ADD 失败要再用
        NIM_MODIFY 探一下：MODIFY 成功说明图标本来就在（比如刚发 TaskbarCreated
        但 Explorer 还没真的清空）。两边都失败才算真没挂上，才继续重试。
        """
        missing = False
        for index, info in enumerate(self.runtime.results):
            if index in self._added:
                continue
            if not self.icons.get(index):
                self.icons[index] = make_battery_icon(None, dim=True)
            tip = f'余量 · {info["name"]} · 读取中'
            if self._notify(NIM_ADD, index, tip) or self._notify(NIM_MODIFY, index, tip):
                self._added.add(index)
            else:
                missing = True
        if self.hwnd:
            if missing:
                user32.SetTimer(self.hwnd, TIMER_RETRY, 2000, None)
            else:
                user32.KillTimer(self.hwnd, TIMER_RETRY)

    def _apply_icons(self):
        self._reap()
        for index, info in enumerate(self.runtime.results):
            percent = info.get("percent")
            charging = bool(info.get("charging"))
            stale = percent is None and info.get("last")
            if stale:
                percent = info["last"].get("percent")
                charging = bool(info["last"].get("charging"))
            dim = info.get("state") != "ok"

            new = make_battery_icon(percent, charging=charging, dim=dim)
            if not new:
                continue
            old = self.icons.get(index)
            self.icons[index] = new
            if old and old != new:
                self._graveyard.append((time.time() + ICON_TTL, old))

            if percent is None:
                tip = f'余量 · {info["name"]} · 未读'
            elif stale:
                tip = (f'余量 · {info["name"]} · {percent}%'
                       f'（休眠中，上次 {info["last"].get("time", "")}）')
            else:
                tip = f'余量 · {info["name"]} · {percent}%'
                if charging:
                    tip += "（充电中）"

            if index in self._added and self._notify(NIM_MODIFY, index, tip):
                continue
            self._added.discard(index)          # 通知区里可能已经没我们了
            if self._notify(NIM_ADD, index, tip) or self._notify(NIM_MODIFY, index, tip):
                self._added.add(index)
        if len(self._added) < len(self.runtime.results):
            user32.SetTimer(self.hwnd, TIMER_RETRY, 2000, None)

    def _reap(self):
        if not self._graveyard:
            return
        now = time.time()
        alive = []
        for when, handle in self._graveyard:
            if when <= now:
                user32.DestroyIcon(handle)
            else:
                alive.append((when, handle))
        self._graveyard = alive

    # ------------------------------------------------ 线程
    def run(self):
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSW()
        wc.lpfnWndProc = ctypes.cast(self._proc, ctypes.c_void_p)
        wc.hInstance = hinst
        wc.lpszClassName = CLASS_NAME
        if not user32.RegisterClassW(ctypes.byref(wc)):
            err = ctypes.get_last_error()
            if err not in (1410,):        # 已经注册过
                self.runtime.note(f"托盘窗口类注册失败: {err}")
        self.hwnd = user32.CreateWindowExW(0, CLASS_NAME, "PeripheralBatteryTrayHidden",
                                           0, 0, 0, 0, 0, None, None, hinst, None)
        if not self.hwnd:
            self.runtime.note("托盘窗口创建失败")
            return
        # TaskbarCreated 也要能被这个窗口收到，所以窗口类别名注册即可（广播消息）
        self.runtime.tray_hwnd = self.hwnd
        for index in range(len(self.runtime.results)):
            self.icons[index] = make_battery_icon(None, dim=True)
        self._ensure_icons()
        user32.SetTimer(self.hwnd, 1, max(10, self.runtime.config["interval"]) * 1000, None)
        self.ready.set()

        msg = w.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def restart_timer(self, seconds):
        if self.hwnd:
            user32.KillTimer(self.hwnd, 1)
            user32.SetTimer(self.hwnd, 1, max(10, seconds) * 1000, None)

    def refresh_icons(self):
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_REFRESH_ICONS, 0, 0)


# ----------------------------------------------------------------- 运行时
class Runtime:
    def __init__(self, debug=False):
        self.config = load_config()
        self.debug = debug
        self.results = [dict(spec, percent=None, charging=None, state="pending",
                             detail="尚未读取", time="")
                        for spec in protocols.DEVICES]
        self.tray_hwnd = None
        self.panel_queue = queue.Queue()
        self._refresh = threading.Event()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._interfaces = []
        self.trace_lines = []
        self.tray = None
        self.busy = False
        self.stamp = 0
        self.on_show = None
        self.on_quit = None
        self.quitting = False
        self._last_good = {}

    # --- 线程间指令
    def note(self, text):
        if self.debug:
            print("[tray]", text)

    def request_refresh(self, reason=""):
        self._refresh.set()

    def request_panel(self):
        self.panel_queue.put("show")
        if self.on_show:
            try:
                self.on_show()
            except Exception:
                pass

    def request_quit(self):
        self.quitting = True
        self.panel_queue.put("quit")
        if self.on_quit:
            try:
                self.on_quit()
            except Exception:
                pass

    # --- 采集线程
    def worker(self):
        while not self._stop.is_set():
            # 有设备读不到时缩短轮询间隔，等它醒来立刻抓到
            wait = 15 if self._needs_retry() else max(10, int(self.config.get("interval", 60)))
            triggered = self._refresh.wait(wait)
            if self._stop.is_set():
                return
            if not triggered and not self._needs_retry():
                continue
            self._refresh.clear()
            try:
                self._interfaces = hidlib.enumerate_interfaces()
                results = protocols.read_all(self._interfaces,
                                             trace=self._record_trace)
            except Exception:
                results = [dict(spec, percent=None, charging=None, state="error",
                                detail="读取异常", time=time.strftime("%H:%M:%S"))
                           for spec in protocols.DEVICES]
                if self.debug:
                    traceback.print_exc()
            with self._lock:
                self.stamp += 1
            # 休眠 / 无响应时，把上一次读到的值带上，界面不至于变空
            for index, info in enumerate(results):
                if info.get("percent") is not None:
                    self._last_good[index] = {
                        "percent": info["percent"],
                        "charging": info.get("charging"),
                        "time": info.get("time"),
                    }
                elif index in self._last_good:
                    info["last"] = self._last_good[index]
            with self._lock:
                self.results = results
            self.panel_queue.put("update")
            if self.tray:
                self.tray.refresh_icons()

    def results_stale(self):
        return all(r.get("state") == "pending" for r in self.results)

    def _needs_retry(self):
        """还有设备没读到（休眠/未回应）→ 快一点重试。"""
        if self.results_stale():
            return True
        return any(info.get("percent") is None for info in self.results)

    def _record_trace(self, iface, direction, data):
        if not self.debug:
            return
        text = " ".join(f"{b:02X}" for b in data[:24])
        self.trace_lines.append(f"{direction} {text}")
        self.trace_lines = self.trace_lines[-200:]

    def snapshot(self):
        with self._lock:
            return [dict(r) for r in self.results]

    def interfaces(self):
        return list(self._interfaces)


# ----------------------------------------------------------------- 面板
# ----------------------------------------------------------------- 调试窗口
class DebugWindow:
    def __init__(self, master, runtime):
        self.runtime = runtime
        self.top = tk.Toplevel(master)
        self.top.title(f"{APP_NAME} · 调试")
        self.top.configure(bg=T.PAPER)
        self.top.geometry("760x520")

        left = tk.Frame(self.top, bg=T.PAPER)
        left.pack(side="left", fill="both", expand=False, padx=(16, 8), pady=16)
        tk.Label(left, text="HID 接口", bg=T.PAPER, fg=T.INK,
                 font=(T.UI_FONT_SEMI, 10)).pack(anchor="w")
        self.listbox = tk.Listbox(left, width=40, height=22, bd=0, bg=T.CARD,
                                  fg=T.INK_SOFT, highlightthickness=1,
                                  highlightbackground=T.BORDER, selectbackground=T.ACCENT_SOFT,
                                  selectforeground=T.INK, font=("Consolas", 9))
        self.listbox.pack(fill="both", expand=True, pady=(6, 6))
        self.listbox.bind("<<ListboxSelect>>", self.on_select)
        self._flat_button(left, "重新枚举", self.reload).pack(anchor="w")
        self._flat_button(left, "转储输入报告（2 秒）", self.dump_reports).pack(anchor="w", pady=(6, 0))

        right = tk.Frame(self.top, bg=T.PAPER)
        right.pack(side="left", fill="both", expand=True, padx=(8, 16), pady=16)
        self.detail = tk.Text(right, height=10, bd=0, bg=T.CARD, fg=T.INK_SOFT,
                              highlightthickness=1, highlightbackground=T.BORDER,
                              font=("Consolas", 9), wrap="none")
        self.detail.pack(fill="both", expand=True, pady=(0, 8))
        self.trace = tk.Text(right, height=12, bd=0, bg="#FBFAF6", fg=T.INK_SOFT,
                             highlightthickness=1, highlightbackground=T.BORDER,
                             font=("Consolas", 9), wrap="none")
        self.trace.pack(fill="both", expand=True)

        self._ifaces = []
        self.reload()

    def _flat_button(self, parent, text, command):
        return tk.Button(parent, text=text, command=command, bg=T.CARD, fg=T.INK_SOFT,
                         activebackground=T.CARD_ALT, relief="flat", bd=0, padx=12,
                         pady=4, cursor="hand2", font=(T.UI_FONT, 9),
                         highlightthickness=1)

    def reload(self):
        self._ifaces = hidlib.enumerate_interfaces()
        self.listbox.delete(0, "end")
        for rec in sorted(self._ifaces, key=lambda r: (r.vid, r.pid, r.usage_page or 0)):
            self.listbox.insert("end",
                                f'{rec.vid:04X}:{rec.pid:04X} up=0x{(rec.usage_page or 0):04X} '
                                f'{rec.product or rec.desc or ""}')

    def on_select(self, _event=None):
        sel = self.listbox.curselection()
        if not sel:
            return
        rec = sorted(self._ifaces, key=lambda r: (r.vid, r.pid, r.usage_page or 0))[sel[0]]
        lines = [
            f"路径        {rec.path}",
            f"VID:PID     {rec.vid:04X}:{rec.pid:04X}",
            f"产品        {rec.product!r}",
            f"厂商        {rec.manufacturer!r}",
            f"序列号      {rec.serial!r}",
            f"UsagePage   0x{(rec.usage_page or 0):04X}  Usage 0x{(rec.usage or 0):04X}",
            f"报告长度    in={rec.in_len} out={rec.out_len} feature={rec.feat_len}",
            f"描述        {rec.desc!r}",
        ]
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", "\n".join(lines))

    def dump_reports(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        rec = sorted(self._ifaces, key=lambda r: (r.vid, r.pid, r.usage_page or 0))[sel[0]]
        self.trace.insert("end", f"\n--- 读取 {rec.product or rec.key} 2 秒 ---\n")
        self.trace.see("end")

        def run():
            try:
                with rec.open(read=True, write=False) as h:
                    if not h.ok:
                        self.top.after(0, lambda: self.trace.insert("end", "打开失败\n"))
                        return
                    end = time.time() + 2
                    while time.time() < end:
                        data = h.read(300)
                        if data:
                            text = " ".join(f"{b:02X}" for b in data)
                            self.top.after(0, lambda t=text: self.trace.insert("end", t + "\n"))
            except Exception as exc:
                self.top.after(0, lambda: self.trace.insert("end", f"异常 {exc}\n"))

        threading.Thread(target=run, daemon=True).start()


# ----------------------------------------------------------------- 主程序
def once(debug=False):
    interfaces = hidlib.enumerate_interfaces()
    results = protocols.read_all(interfaces, trace=None)
    for info in results:
        if info["percent"] is None:
            print(f'{info["name"]}: {info["detail"]}')
        else:
            print(f'{info["name"]}: {info["percent"]}%'
                  f'{"（充电中）" if info["charging"] else "（未充电）"}')
    return results


def main():
    parser = argparse.ArgumentParser(description="外设电量小工具")
    parser.add_argument("--once", action="store_true", help="读取一次并打印")
    parser.add_argument("--panel", action="store_true", help="只开面板")
    parser.add_argument("--debug", action="store_true", help="输出调试信息")
    parser.add_argument("--install", action="store_true",
                        help="在桌面创建快捷方式（不复制脚本）")
    parser.add_argument("--autostart", choices=["on", "off"],
                        help="开启 / 关掉开机自启")
    args = parser.parse_args()

    ctypes.windll.ole32.CoInitialize(None)

    if args.install or args.autostart:
        if args.install:
            ok = write_shortcut(desktop_lnk_path())
            print("桌面快捷方式：", "已创建" if ok else "创建失败")
        if args.autostart:
            ok = set_autostart(args.autostart == "on")
            print("开机自启：", "已开启" if (ok and args.autostart == "on") else
                  ("已关闭" if (ok and args.autostart == "off") else "设置失败"))
        return

    # 注意：Tk 8.6 在「进程 DPI 感知 + 系统缩放 125%/150%」的组合下会把窗口按
    # 物理像素缩小，导致内容被裁切。这里不声明 DPI 感知，交给系统整体缩放，
    # 托盘图标的清晰度由 icons.py 按系统小图标尺寸补齐。
    if args.once:
        once(args.debug)
        return

    mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    already = ctypes.get_last_error() == 183
    if already:
        hwnd = user32.FindWindowW(CLASS_NAME, None)
        if hwnd:
            user32.PostMessageW(hwnd, WM_SHOW_PANEL, 0, 0)
        else:
            ctypes.windll.user32.MessageBoxW(None, "外设电量已经在运行（面板被隐藏）。",
                                             APP_NAME, 0x40)
        return

    runtime = Runtime(debug=args.debug)
    import webapp
    webapp.run_with(runtime, panel_only=args.panel)


if __name__ == "__main__":
    main()
