"""读键盘/接收器的 RDR 版本号（0x12 deviceInfo），刷固件前后对比用。"""
import hidlib
from probe1k import Chan


def read_info(ifaces):
    rec = hidlib.find_interface(ifaces, 0x36B0, 0x3002, 0xFF60)
    if rec is None:
        return None
    ch = Chan(rec.path, 33, 33)
    if not ch.ok:
        return None

    def send(cmd, off=0, ln=24, wait=0.7):
        import time
        buf = bytearray(33)
        buf[1] = 0xAA
        buf[2] = cmd
        buf[3] = off & 0xFF
        buf[4] = (off >> 8) & 0xFF
        buf[5] = ln
        ch.write(bytes(buf))
        end = time.time() + wait
        while time.time() < end:
            data = ch.read(200)
            if not data:
                continue
            f = data[1:] if data[0] == 0x00 else data
            if len(f) > 7 and f[0] == 0xAA and f[1] == cmd:
                return f
        return None

    try:
        if not send(0x10):
            return None
        payload = b""
        for off in (0, 24, 48):
            f = send(0x12, off, 24)
            if not f:
                break
            payload += f[8:8 + 24]
        send(0x11, wait=0.3)
    finally:
        ch.close()
    return payload


def main():
    payload = read_info(hidlib.enumerate_interfaces())
    if not payload:
        print("读不到（键盘休眠中）")
        return
    print("deviceInfo 前 30 字节:", " ".join(f"{b:02X}" for b in payload[:30]))
    if len(payload) >= 8:
        vid = payload[2] | payload[3] << 8
        pid = payload[4] | payload[5] << 8
        fw_lo, fw_hi = payload[6], payload[7]
        print(f"  vid/pid    = {vid:04X}:{pid:04X}")
        print(f"  firmwareVer= 0x{fw_hi:02X}{fw_lo:02X}  ({fw_hi}.{fw_lo})")


if __name__ == "__main__":
    main()
