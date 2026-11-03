"""核对两台设备的充电标志原始字节。"""
import hidlib
import protocols

ifaces = hidlib.enumerate_interfaces()
results = protocols.read_all(ifaces)
for r in results:
    print(f"{r['name']:12s} percent={r.get('percent')!s:>5} "
          f"charging={r.get('charging')!s:>5} state={r.get('state')}")
    if r.get("raw_byte") is not None:
        print(f"             原始字节 = 0x{r['raw_byte']:02X}")
