"""两个外设的电量协议（都是从官方驱动里逆向出来的实测参数）。

1) 贱驴 James Donkey A3 HE（Ultra-Link 8K 接收器 362D:D028）
   接口 usage page 0xFFC1，64 字节报文：
     请求  report id 0xB3 + 载荷[0]=0x06（"取基础信息"）
     回复  report id 0xB4，载荷[0]==0x06
           载荷[19] 低 7 位 = 电量百分比，最高位 = 是否在充电
   顺带能拿到：载荷[18] = 休眠分钟数，载荷[2..4] = DPI 档位。

2) PMO P75（RDR 2.4G 接收器 36B0:3002）
   接口 usage page 0xFF00，帧格式 [rid, 0xAA, cmd, offLo, offHi, len, ...]：
     0x10 开始通讯 / 0x12 设备信息 / 0x30 电池 / 0x11 结束通讯
     回复里 0x55 表示成功，数据从第 8 字节开始，电池帧 data[8]=电量、data[9]=充电。
"""
import time

from hidlib import find_interface

# --- 设备定义 -------------------------------------------------------------
JD_MOUSE = dict(
    key="mouse",
    name="贱驴 RSR5S",
    source="Ultra-Link 8K 接收器",
    vid=0x362D, pid=0xD028, usage_page=0xFFC1,
)
PMO_KEYBOARD = dict(
    key="keyboard",
    name="PMO P75",
    source="RDR 2.4G 接收器",
    vid=0x36B0, pid=0x3002, usage_page=0xFF00,
    # 有线模式 / 其他 RDR 键盘（插线或换键盘时也能认出来）
    alt=[(0x36B0, 0x302B, 0xFF00), (0x36B0, 0x3012, 0xFF00),
         (0x36B0, 0x3004, 0xFF00), (0x36B0, 0x3009, 0xFF00)],
)
DEVICES = [JD_MOUSE, PMO_KEYBOARD]

# RDR 接收器可能配对的键盘 pid（P75 / PMO 80 / Aurora 80 / WAVE 75）
PAIRED_PIDS = {0x302B, 0x3012, 0x3004, 0x3009}


# --- 贱驴鼠标 -------------------------------------------------------------
JD_REQ_ID = 0xB3
JD_REP_ID = 0xB4
JD_CMD_BASE = 0x06
JD_BATTERY_AT = 19        # 载荷内下标（不含 report id）


def read_jd_mouse(iface, trace=None, interfaces=None):
    result = {"percent": None, "charging": None, "state": "error", "detail": ""}
    if iface is None:
        result["detail"] = "未检测到 Ultra-Link 8K 接收器"
        result["state"] = "disconnected"
        return result

    with iface.open(read=True, write=True) as h:
        if not h.ok:
            result["detail"] = "接收器被占用，无法打开"
            return result
        for attempt in range(3):
            h.drain()
            req = bytearray(64)
            req[0] = JD_REQ_ID
            req[1] = JD_CMD_BASE
            if not h.write_raw(req):
                result["detail"] = "写入接收器失败"
                continue
            deadline = time.time() + 1.2
            while time.time() < deadline:
                data = h.read(400)
                if data is None:
                    break
                if trace:
                    trace(iface, "RX", data)
                if len(data) < JD_BATTERY_AT + 2:
                    continue
                if data[0] != JD_REP_ID or data[1] != JD_CMD_BASE:
                    continue
                raw = data[1 + JD_BATTERY_AT]
                result.update(percent=raw & 0x7F, charging=bool(raw >> 7),
                              state="ok", detail="")
                return result
            if attempt < 2:
                time.sleep(0.15)
    if not result["detail"]:
        result["detail"] = "接收器无回应（鼠标已休眠，动一下鼠标就更新）"
        result["state"] = "sleep"
    return result


# --- PMO 键盘 -------------------------------------------------------------
PMO_MARK = 0xAA
PMO_START, PMO_STOP, PMO_INFO, PMO_FUNC, PMO_BATTERY = 0x10, 0x11, 0x12, 0x14, 0x30
PMO_OK = 0x55
PMO_OUT_IDS = (0x3F, 0x00)     # 实测只有 0x3F 被接收，0x00 兜底给别的固件
PMO_CHUNK = 24                 # 2.4G 模式的分片长度


def _pmo_frame(rid, cmd, offset=0, length=PMO_CHUNK, size=64):
    buf = bytearray(size)
    buf[0] = rid
    buf[1] = PMO_MARK
    buf[2] = cmd
    buf[3] = offset & 0xFF
    buf[4] = (offset >> 8) & 0xFF
    buf[5] = length
    return buf


def _pmo_match(data, cmd, offset=0, length=PMO_CHUNK):
    """在回复里找帧头，返回 (frame, status) 或 None。"""
    for shift in (0, 1):
        if len(data) < shift + 8:
            continue
        f = data[shift:]
        if f[0] != PMO_MARK or f[1] != cmd:
            continue
        if f[2] != (offset & 0xFF) or f[3] != ((offset >> 8) & 0xFF) or f[4] != length:
            continue
        return f, f[7]
    return None


def _pmo_cmd(h, rid, cmd, offset=0, length=PMO_CHUNK, timeout=1.0, trace=None):
    if not h.write(_pmo_frame(rid, cmd, offset, length)):
        return None
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = h.read(300)
        if data is None:
            break
        if trace:
            trace(None, f"RX cmd=0x{cmd:02X}", data)
        hit = _pmo_match(data, cmd, offset, length)
        if hit:
            return hit
    return None


def read_pmo_keyboard(iface, trace=None, interfaces=None):
    result = {"percent": None, "charging": None, "state": "error", "detail": ""}
    if iface is None:
        result["detail"] = "未检测到 RDR 2.4G 接收器"
        result["state"] = "disconnected"
        return result

    # 两个可能的主通道都试：0xFF60（32 字节帧，实测这个才是通的）和 0xFF00（64 字节）
    channels = []
    if interfaces:
        alt = find_interface(interfaces, PMO_KEYBOARD["vid"], PMO_KEYBOARD["pid"], 0xFF60)
        if alt is not None:
            channels.append((alt, (0x00,)))
    channels.append((iface, PMO_OUT_IDS))

    detail = ""
    for chan, rids in channels:
        with chan.open(read=True, write=True) as h:
            if not h.ok:
                detail = "接收器被占用，无法打开"
                continue
            for rid in rids:
                h.drain()
                # 关键：必须先 0x10 握手拿到 0x55，否则后面的命令一律回 0x0F
                if not _pmo_cmd(h, rid, PMO_START, length=PMO_CHUNK, timeout=0.8,
                                trace=trace):
                    detail = detail or "握手无回应（键盘休眠中）"
                    continue
                try:
                    for _attempt in range(3):
                        hit = _pmo_cmd(h, rid, PMO_BATTERY, 0, PMO_CHUNK,
                                       timeout=0.6, trace=trace)
                        if not hit:
                            time.sleep(0.12)
                            continue
                        frame, status = hit
                        if status == PMO_OK and len(frame) >= 10 and 0 <= frame[8] <= 100:
                            result.update(percent=frame[8],
                                          charging=bool(frame[9]),
                                          state="ok", detail="")
                            return result
                        detail = f"键盘回复状态 0x{status:02X}"
                finally:
                    _pmo_cmd(h, rid, PMO_STOP, timeout=0.3)

    # 退一步：用接收器自己的状态通道判断键盘是不是根本没上线
    alive = _pmo_presence(interfaces, trace)
    if alive:
        result.update(state="idle",
                      detail=detail or "键盘已配对但不响应电量查询（按一下键唤醒再试）")
    elif alive is False:
        result.update(state="idle",
                      detail="接收器在线，键盘无回应（关机 / 休眠 / 未切到 2.4G）")
    elif not result["detail"]:
        result["detail"] = detail or "键盘无回应（确认键盘已开机并处于 2.4G 模式）"
    return result


# --- 键盘的灯光/休眠配置（诊断用，只读）------------------------------
def read_pmo_funcinfo(iface=None, interfaces=None, trace=None):
    """读 RDR 的 funcInfo（0x14，41 字节）。返回 dict 或 None。

    实测必须先发 0x10（开始通讯）拿到 0x55，否则后续命令一律 0x0F；
    而且真正通的通道是 0xFF60（32 字节帧，report id 0）。
    字段下标来自 PMOHub 的 xr() 解析：
      [1] 灯光开关  [2] 灯效  [3] 亮度  [4] 速度
      [35..37] sleepTime（LE24，分钟）  [38..40] deepSleepTime（LE24，分钟）
    """
    chan = iface
    if interfaces:
        alt = find_interface(interfaces, PMO_KEYBOARD["vid"], PMO_KEYBOARD["pid"], 0xFF60)
        if alt is not None:
            chan = alt
    if chan is None:
        return None
    with chan.open(read=True, write=True) as h:
        if not h.ok:
            return None
        h.drain()
        if not _pmo_cmd(h, 0x00, PMO_START, length=PMO_CHUNK, timeout=0.8, trace=trace):
            return None
        try:
            # funcInfo 有 41 字节，而 32 字节帧一帧只装 24 字节 → 按 offset 分片读
            total = 41
            data = bytearray()
            offset = 0
            while len(data) < total:
                want = min(PMO_CHUNK, total - len(data))
                hit = _pmo_cmd(h, 0x00, PMO_FUNC, offset, want, timeout=0.8, trace=trace)
                if not hit:
                    return None
                frame, status = hit
                if status != PMO_OK:
                    return None
                chunk = frame[8:8 + want]
                if not chunk:
                    return None
                data += chunk
                offset += len(chunk)
            data = bytes(data[:total])

            def le24(b):
                """三个字节的值。0xFFFF 开头 = 未设置（固件用 FF FF 当无效标记）。"""
                if b[0] == 0xFF and b[1] == 0xFF:
                    return None
                return b[0] | (b[1] << 8) | (b[2] << 16)

            return {
                "light_switch": data[1],
                "light_mode": data[2],
                "brightness": data[3],
                "speed": data[4],
                "scan_delay": data[33],
                "layer_default": data[34],
                "sleep_minutes": le24(data[35:38]),
                "deep_sleep_minutes": le24(data[38:41]),
                "raw": " ".join(f"{b:02X}" for b in data),
            }
        finally:
            _pmo_cmd(h, 0x00, PMO_STOP, timeout=0.3)
    return None


def _pmo_presence(interfaces, trace=None):
    """0xFF60 通道上的 0xD0 轮询：能拿到回复说明接收器在，但键盘未必醒着。"""
    """0xFF60 通道上的 0xD0 轮询：能拿到回复说明接收器在，但键盘未必醒着。"""
    if not interfaces:
        return None
    iface = find_interface(interfaces, PMO_KEYBOARD["vid"], PMO_KEYBOARD["pid"], 0xFF60)
    if iface is None:
        return None
    with iface.open(read=True, write=True) as h:
        if not h.ok:
            return None
        h.drain()
        buf = bytearray(33)
        buf[0] = 0x00
        buf[1] = PMO_MARK
        buf[2] = 0xD0
        buf[3] = 0x00
        buf[4] = 0x00
        buf[5] = 0x18
        if not h.write_raw(buf):
            return None
        deadline = time.time() + 0.8
        while time.time() < deadline:
            data = h.read(250)
            if data is None:
                break
            if trace:
                trace(iface, "RX(0xD0)", data)
            if len(data) >= 8 and data[1] == PMO_MARK and data[2] == 0xD0:
                pvid = data[10] | (data[11] << 8)
                ppid = data[12] | (data[13] << 8)
                return pvid == PMO_KEYBOARD["vid"] and ppid in PAIRED_PIDS
    return False


# --- 统一入口 -------------------------------------------------------------
READERS = {"mouse": read_jd_mouse, "keyboard": read_pmo_keyboard}


def read_all(interfaces, trace=None):
    """返回 [{key,name,source,percent,charging,state,detail,found}, ...]"""
    out = []
    for spec in DEVICES:
        iface = find_interface(interfaces, spec["vid"], spec["pid"], spec["usage_page"])
        if iface is None:
            for vid, pid, up in spec.get("alt", ()):
                iface = find_interface(interfaces, vid, pid, up)
                if iface is not None:
                    break
        info = dict(spec)
        info.pop("alt", None)
        info["found"] = iface is not None
        try:
            res = READERS[spec["key"]](iface, trace=trace, interfaces=interfaces)
        except Exception as exc:               # 协议层绝不把异常抛给界面
            res = {"percent": None, "charging": None, "state": "error",
                   "detail": f"{type(exc).__name__}: {exc}"}
        info.update(res)
        info["time"] = time.strftime("%H:%M:%S")
        out.append(info)
    return out
