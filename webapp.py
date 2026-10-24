"""WebView2 界面：HTML/CSS 渲染，Python 只负责 HID、托盘和状态。

要点（踩过的坑）：
* pywebview 会把 js_api 对象上的「公开属性」也当桥暴露出去，所以内部状态
  一律加下划线（_runtime/_window/...），否则它会去递归 introspection
  一个 Window 对象，触发 COM 递归爆栈。
* WebView2 的 UI 线程限制：后台线程不能碰 window.evaluate_js，
  所以数据改由前端 600ms 轮询 api.state()。
* 托盘点击回到前台用 Win32 ShowWindow，不走 pywebview 的 native 对象。
"""
import ctypes
import json
import os
import sys
import threading
import time

import hidlib
import protocols
import webview
from periph_battery import (APP_NAME, INTERVALS, Runtime, Tray, autostart_enabled,
                            save_config, set_autostart)

WINDOW_W, WINDOW_H = 1000, 680


def resource_path(*parts):
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, *parts)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), *parts)


def load_html():
    with open(resource_path("ui", "index.html"), "r", encoding="utf-8") as handle:
        return handle.read()


def webview_storage_dir():
    """WebView2 的独立 user data 目录。

    不指定的话会跟系统 Edge 共用浏览器进程，实测会把我们的窗口变成一个
    158×26 的空壳，界面跑到 Edge 的 InPrivate 窗口里。
    """
    base = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
                        "PeripheralBattery", "WebView2")
    os.makedirs(base, exist_ok=True)
    return base


class Api:
    """只暴露下面这些公开方法给前端（内部状态全部下划线开头）。"""

    def __init__(self, runtime):
        self._runtime = runtime
        self._selected = 0
        self._interfaces = []

    # ---------------------------------------------------------- 状态
    def _snapshot(self):
        results = self._runtime.snapshot()
        for info in results:
            info.pop("alt", None)
        return {
            "devices": results,
            "interval": int(self._runtime.config.get("interval", 60)),
            "autostart": autostart_enabled(),
            "busy": bool(self._runtime.busy),
            "selected": self._selected,
        }

    def state(self):
        if self._runtime.debug:
            try:
                with open(os.path.join(os.environ.get("TEMP", "."), "pb-bridge.txt"),
                          "a", encoding="utf-8") as fh:
                    fh.write(f"{time.time():.3f}\n")
            except Exception:
                pass
        return self._snapshot()

    # ---------------------------------------------------------- 动作
    def refresh(self):
        self._runtime.busy = True
        self._runtime.request_refresh("手动刷新")
        stamp = self._runtime.stamp
        deadline = time.time() + 6
        while time.time() < deadline and self._runtime.stamp == stamp:
            time.sleep(0.05)
        self._runtime.busy = False
        return self._snapshot()

    def select(self, index):
        self._selected = max(0, int(index))
        return self._snapshot()

    def cycle_interval(self):
        values = [secs for _label, secs in INTERVALS]
        current = int(self._runtime.config.get("interval", 60))
        try:
            nxt = values[(values.index(current) + 1) % len(values)]
        except ValueError:
            nxt = 60
        self._runtime.config["interval"] = nxt
        save_config(self._runtime.config)
        if self._runtime.tray:
            self._runtime.tray.restart_timer(nxt)
        return self._snapshot()

    def toggle_autostart(self):
        set_autostart(not autostart_enabled())
        return self._snapshot()

    def quit(self):
        runtime = self._runtime
        runtime.quitting = True
        if runtime.tray and runtime.tray.hwnd:
            from periph_battery import WM_DESTROY, user32
            user32.PostMessageW(runtime.tray.hwnd, WM_DESTROY, 0, 0)
        runtime._stop.set()
        runtime._refresh.set()
        _post_close()
        return True

    # ---------------------------------------------------------- 调试
    def hid_list(self):
        self._interfaces = hidlib.enumerate_interfaces()
        rows = []
        for rec in sorted(self._interfaces,
                          key=lambda r: (r.vid, r.pid, r.usage_page or 0)):
            rows.append({"label": (f"0x{rec.vid:04X}:0x{rec.pid:04X}  "
                                   f"up=0x{(rec.usage_page or 0):04X}  "
                                   f"{rec.product or rec.desc or ''}")})
        return rows

    def _pick(self, index):
        ordered = sorted(self._interfaces,
                         key=lambda r: (r.vid, r.pid, r.usage_page or 0))
        return ordered[int(index)]

    def hid_detail(self, index):
        rec = self._pick(index)
        return "\n".join([
            f"路径      {rec.path}",
            f"VID:PID   0x{rec.vid:04X}:0x{rec.pid:04X}",
            f"产品      {rec.product!r}",
            f"厂商      {rec.manufacturer!r}",
            f"序列号    {rec.serial!r}",
            f"Usage     0x{(rec.usage_page or 0):04X} / 0x{(rec.usage or 0):04X}",
            f"报告长度  in={rec.in_len}  out={rec.out_len}  feature={rec.feat_len}",
            f"描述      {rec.desc!r}",
        ])

    def pmo_config(self):
        """键盘的灯光 / 休眠配置（给调试面板对比「关灯前后」用）。"""
        iface = hidlib.find_interface(hidlib.enumerate_interfaces(),
                                       0x36B0, 0x3002, 0xFF00)
        info = protocols.read_pmo_funcinfo(iface, hidlib.enumerate_interfaces())
        if not info:
            return "读不到（键盘休眠中，先按几下键盘唤醒）"
        def fmt(value, unit=""):
            return "未设置" if value is None else f"{value}{unit}"
        return "\n".join([
            f"灯光开关  {info['light_switch']}  （0=关 1=开）",
            f"灯效/亮度 {info['light_mode']} / {info['brightness']}",
            f"休眠时间  {fmt(info['sleep_minutes'], ' 分钟')}",
            f"深度休眠  {fmt(info['deep_sleep_minutes'], ' 分钟')}",
            "",
            "原始 41 字节:",
            info["raw"],
        ])

    def dump_reports(self, index):
        rec = self._pick(index)
        lines = []
        try:
            with rec.open(read=True, write=False) as handle:
                if not handle.ok:
                    return ["打开失败（可能被独占）"]
                end = time.time() + 2
                while time.time() < end:
                    data = handle.read(300)
                    if data:
                        lines.append(" ".join(f"{b:02X}" for b in data))
        except Exception as exc:
            lines.append(f"异常：{exc}")
        return lines


# ---------------------------------------------------------------- 界面
def run():
    run_with(Runtime(debug="--debug" in sys.argv), panel_only="--panel" in sys.argv)


def run_with(runtime, panel_only=False):
    api = Api(runtime)
    threading.Thread(target=runtime.worker, daemon=True).start()

    window = webview.create_window(
        APP_NAME,
        html=load_html(),
        width=WINDOW_W,
        height=WINDOW_H,
        resizable=False,
        background_color="#F4F0E7",
        js_api=api,
    )
    runtime.on_show = _win32_show
    runtime.on_quit = _post_close

    def on_closing():
        """点窗口右上角的 X：默认收进托盘；--panel 模式没有托盘，就直接退出。"""
        if runtime.quitting or panel_only:
            return True
        try:
            window.hide()
        except Exception:
            pass
        return False

    try:
        window.events.closing += on_closing
    except Exception:
        pass

    def pump():
        while not runtime._stop.is_set():
            try:
                kind = runtime.panel_queue.get(timeout=0.25)
            except Exception:
                continue
            if kind == "show":
                _win32_show()

    def after_start():
        """界面起来之后再挂托盘；同时盯 10 秒窗口尺寸（pywebview 偶发 158×26 竞争）。"""
        def watch_size():
            for _ in range(33):          # 10 秒内每 300ms 检查一次
                try:
                    if _fix_window_size():
                        _log("[webapp] 窗口尺寸异常，已纠正")
                except Exception:
                    pass
                time.sleep(0.3)

        threading.Thread(target=watch_size, daemon=True).start()
        if not panel_only:
            tray = Tray(runtime)
            runtime.tray = tray
            tray.start()
            tray.ready.wait(5)
        threading.Thread(target=pump, daemon=True).start()
        runtime.request_refresh("启动")

    # 注意：pywebview 的 debug=True 会拉起 devtools 并把窗口挤成 158×26，
    # 所以我们的 --debug 只控制自己的终端输出，不交给 pywebview。
    webview.start(after_start, storage_path=webview_storage_dir())
    runtime.quitting = True
    runtime._stop.set()
    runtime._refresh.set()


def _log(text):
    """--windowed 打包后 stdout 是 None，print 会抛异常，统一走这里。"""
    try:
        if sys.stderr is not None:
            print(text, file=sys.stderr, flush=True)
    except Exception:
        pass


def _win32_show():
    from periph_battery import user32
    try:
        hwnd = user32.FindWindowW(None, APP_NAME)
        if hwnd:
            _fix_window_size(hwnd)
            user32.ShowWindow(hwnd, 9)
            user32.SetForegroundWindow(hwnd)
    except Exception:
        pass


def _fix_window_size(hwnd=None):
    """pywebview 偶尔会把窗口建成 158×26（尺寸竞争），这里发现就拉回目标大小。"""
    from ctypes import wintypes as wt
    from periph_battery import user32

    class _RECT(ctypes.Structure):
        _fields_ = [("l", wt.LONG), ("t", wt.LONG), ("r", wt.LONG), ("b", wt.LONG)]

    try:
        if not hwnd:
            hwnd = user32.FindWindowW(None, APP_NAME)
        if not hwnd:
            return False
        rect = _RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        width, height = rect.r - rect.l, rect.b - rect.t
        if width >= 600 and height >= 400:
            return False
        # 未声明 DPI 感知，坐标是虚拟像素；按屏幕比例算目标尺寸
        screen_w = user32.GetSystemMetrics(0) or 1920
        screen_h = user32.GetSystemMetrics(1) or 1080
        want_w = min(WINDOW_W, int(screen_w * 0.82))
        want_h = min(WINDOW_H, int(screen_h * 0.86))
        user32.SetWindowPos(hwnd, None, 0, 0, want_w, want_h, 0x0002 | 0x0004)  # NOMOVE|NOZORDER
        return True
    except Exception:
        return False


def _post_close():
    from periph_battery import user32
    try:
        hwnd = user32.FindWindowW(None, APP_NAME)
        if hwnd:
            user32.PostMessageW(hwnd, 0x0010, 0, 0)     # WM_CLOSE
    except Exception:
        pass


if __name__ == "__main__":
    run()

