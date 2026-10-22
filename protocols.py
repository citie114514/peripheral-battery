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

    # 两个可能的主通道都试：0xFF00（64 字节，report id 0x3F）和 0xFF60（32 字节，report id 0）
    channels = [(iface, PMO_OUT_IDS)]
    if interfaces:
        alt = find_interface(interfaces, PMO_KEYBOARD["vid"], PMO_KEYBOARD["pid"], 0xFF60)
        if alt is not None and alt.path != iface.path:
            channels.append((alt, (0x00,)))

    detail = ""
    for chan, rids in channels:
        with chan.open(read=True, write=True) as h:
            if not h.ok:
                detail = "接收器被占用，无法打开"
                continue
            for rid in rids:
                h.drain()
                # 不等 START 的 ack（很多固件不回它），先把电池命令直接怼上去
                for _attempt in range(3):
                    hit = _pmo_cmd(h, rid, PMO_BATTERY, 0, PMO_CHUNK,
                                   timeout=0.5, trace=trace)
                    if hit:
                        frame, status = hit
                        if status == PMO_OK and len(frame) >= 10 and 0 <= frame[8] <= 100:
                            result.update(percent=frame[8], charging=bool(frame[9]),
                                          state="ok", detail="")
                            return result
                        detail = f"键盘回复状态 0x{status:02X}"
                    time.sleep(0.15)
                # 再试一次完整握手（开始通讯 → 设备信息 → 电池）
                if _pmo_cmd(h, rid, PMO_START, length=PMO_CHUNK, timeout=0.6, trace=trace):
                    try:
                        _pmo_cmd(h, rid, PMO_INFO, 0, 56, timeout=0.6, trace=trace)
                        hit = _pmo_cmd(h, rid, PMO_BATTERY, 0, PMO_CHUNK, timeout=0.8,
                                       trace=trace)
                        if hit:
                            frame, status = hit
                            if status == PMO_OK and len(frame) >= 10 and 0 <= frame[8] <= 100:
                                result.update(percent=frame[8],
                                              charging=bool(frame[9]),
                                              state="ok", detail="")
                                return result
                            detail = f"键盘回复状态 0x{status:02X}（不支持该指令）"
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


def _pmo_presence(interfaces, trace=None):
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
