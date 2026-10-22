"""Read the James Donkey A3 HE mouse battery through its 2.4G receiver.

Protocol (reverse engineered from launcher.jamesdonkey.com.cn):
  interface : usage page 0xFFC1, 64-byte reports
  request   : output report id 0xB3, payload[0] = 0x06  ("get base info")
  reply     : input report id 0xB4, payload[0] == 0x06
              payload[19] low 7 bits = battery %, bit 7 = charging
"""
import ctypes
import time

import hid_probe as hp
from probe1k import Chan

VID = 0x362D
PID = 0xD028
REQ_REPORT_ID = 0xB3
REPLY_REPORT_ID = 0xB4
CMD_BASE = 0x06
BATTERY_INDEX = 19          # index inside the report payload (report id excluded)


def find_interface():
    for rec in hp.enumerate_hids():
        if rec.get("vid") == VID and rec.get("pid") == PID and rec.get("usage_page") == 0xFFC1:
            return rec
    return None


def read_battery(rec, retries=3):
    ch = Chan(rec["path"], 64, 64)
    if not ch.ok:
        return None, "无法打开接收器接口 (err=%d)" % ctypes.get_last_error()
    try:
        for _ in range(retries):
            buf = bytearray(64)
            buf[0] = REQ_REPORT_ID
            buf[1] = CMD_BASE
            if not ch.write(bytes(buf)):
                return None, "写入失败"
            deadline = time.time() + 2
            while time.time() < deadline:
                data = ch.read(600)
                if not data:
                    break
                if data[0] != REPLY_REPORT_ID:
                    continue
                payload = data[1:]
                if payload[0] != CMD_BASE:
                    continue
                raw = payload[BATTERY_INDEX]
                return {"percent": raw & 0x7F, "charging": bool(raw >> 7)}, None
        return None, "接收器没有回应，鼠标可能处于休眠或未连接"
    finally:
        ch.close()


if __name__ == "__main__":
    rec = find_interface()
    if not rec:
        print("没有找到 Ultra-Link 8K 接收器 (362D:D028)")
        raise SystemExit(1)
    for i in range(3):
        info, err = read_battery(rec)
        print(f"#{i+1}", info if info else err)
        time.sleep(1)
