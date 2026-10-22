"""Minimal CDP-over-WebSocket client (stdlib only) for hooking an Electron app.

Usage: python cdp_hook.py <port> <exe> <exe-args...>
"""
import base64
import json
import os
import socket
import struct
import subprocess
import sys
import time
import urllib.request


class WS:
    def __init__(self, url):
        # ws://host:port/path
        assert url.startswith("ws://")
        rest = url[5:]
        hostport, _, path = rest.partition("/")
        path = "/" + path
        host, _, port = hostport.partition(":")
        self.sock = socket.create_connection((host, int(port or 80)), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (f"GET {path} HTTP/1.1\r\nHost: {hostport}\r\n"
               f"Upgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.sock.sendall(req.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.sock.recv(4096)
        assert b"101" in buf.split(b"\r\n")[0], buf[:200]
        self.buf = buf.split(b"\r\n\r\n", 1)[1]
        self.next_id = 1

    def _recv_exact(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("closed")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def send(self, payload):
        data = payload.encode()
        header = bytearray([0x81])
        mask = os.urandom(4)
        ln = len(data)
        if ln < 126:
            header.append(0x80 | ln)
        elif ln < 65536:
            header.append(0x80 | 126)
            header += struct.pack(">H", ln)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", ln)
        header += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        self.sock.sendall(bytes(header) + masked)

    def recv(self):
        out = b""
        while True:
            b1, b2 = self._recv_exact(2)
            fin = b1 & 0x80
            op = b1 & 0x0F
            ln = b2 & 0x7F
            if ln == 126:
                ln = struct.unpack(">H", self._recv_exact(2))[0]
            elif ln == 127:
                ln = struct.unpack(">Q", self._recv_exact(8))[0]
            payload = self._recv_exact(ln) if ln else b""
            if op == 0x9:  # ping
                continue
            if op == 0x8:
                raise ConnectionError("ws closed")
            out += payload
            if fin:
                return out.decode("utf-8", "replace")

    def call(self, method, params=None, timeout=25):
        mid = self.next_id
        self.next_id += 1
        self.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        deadline = time.time() + timeout
        while time.time() < deadline:
            msg = json.loads(self.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})
        raise TimeoutError(method)


def find_target(port, tries=40):
    for _ in range(tries):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=2) as r:
                data = json.loads(r.read())
            pages = [t for t in data if t.get("type") == "page"]
            if pages:
                return pages
        except Exception:
            pass
        time.sleep(0.5)
    return []


if __name__ == "__main__":
    port = int(sys.argv[1])
    exe = sys.argv[2]
    args = sys.argv[3:]
    env = dict(os.environ)
    env.pop("ELECTRON_RUN_AS_NODE", None)
    proc = subprocess.Popen([exe] + args + [f"--remote-debugging-port={port}"], env=env)
    print("launched", proc.pid)
    pages = find_target(port)
    print("pages:", [(p["url"][:60], p["webSocketDebuggerUrl"]) for p in pages])
