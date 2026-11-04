"""ws_min.py — 외부 라이브러리 없는 최소 웹소켓 클라이언트 (RFC 6455, wss 전용)
토스증권 실시간 호가·체결(wss://openapi-ws.tossinvest.com/ws/v1)용. 텍스트 프레임·ping/pong·close·조각 프레임 처리.
"""
from __future__ import annotations

import base64
import hashlib
import os
import socket
import ssl
import struct
from urllib.parse import urlparse

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class WSError(Exception):
    pass


class WS:
    def __init__(self, url: str, headers: dict | None = None, timeout: float = 10):
        u = urlparse(url)
        if u.scheme != "wss":
            raise WSError("wss 만 지원")
        self.host, port = u.hostname, u.port or 443
        raw = socket.create_connection((self.host, port), timeout=timeout)
        self.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=self.host)
        key = base64.b64encode(os.urandom(16)).decode()
        req = [f"GET {u.path or '/'}{'?' + u.query if u.query else ''} HTTP/1.1", f"Host: {self.host}", "Upgrade: websocket",
               "Connection: Upgrade", f"Sec-WebSocket-Key: {key}", "Sec-WebSocket-Version: 13"]
        req += [f"{k}: {v}" for k, v in (headers or {}).items()]
        self.sock.sendall(("\r\n".join(req) + "\r\n\r\n").encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            ch = self.sock.recv(4096)
            if not ch:
                raise WSError("handshake: 연결 끊김")
            buf += ch
            if len(buf) > 65536:
                raise WSError("handshake: 응답이 너무 김")
        head, self._buf = buf.split(b"\r\n\r\n", 1)
        lines = head.decode(errors="replace").split("\r\n")
        status = lines[0].split(" ", 2)
        if len(status) < 2 or status[1] != "101":
            code = status[1] if len(status) > 1 else "?"
            hint = " — 허용 IP 미등록" if code == "403" else " — 토큰 문제" if code == "401" else ""
            raise WSError(f"handshake HTTP {code}{hint}")
        hdr = {l.split(":", 1)[0].strip().lower(): l.split(":", 1)[1].strip() for l in lines[1:] if ":" in l}
        want = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
        if hdr.get("sec-websocket-accept") != want:
            raise WSError("handshake: accept 값 불일치")
        self.closed = False
        self._op, self._parts = None, []

    # ── 보내기 (클라이언트 → 서버는 반드시 마스킹) ──
    def _send(self, op: int, data: bytes):
        n = len(data)
        h = bytes([0x80 | op])
        if n < 126:
            h += bytes([0x80 | n])
        elif n < 65536:
            h += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            h += bytes([0x80 | 127]) + struct.pack(">Q", n)
        m = os.urandom(4)
        self.sock.sendall(h + m + bytes(b ^ m[i % 4] for i, b in enumerate(data)))

    def send_text(self, s: str):
        self._send(0x1, s.encode())

    def close(self):
        if not self.closed:
            self.closed = True
            try:
                self._send(0x8, struct.pack(">H", 1000))
            except Exception:
                pass
            try:
                self.sock.close()
            except Exception:
                pass

    # ── 받기 ──
    def _fill(self, n: int):
        """버퍼에 n 바이트가 쌓일 때까지 받기만 함(꺼내지 않음) — 중간에 timeout 이 나도 프레임이 깨지지 않게"""
        while len(self._buf) < n:
            ch = self.sock.recv(65536)
            if not ch:
                raise WSError("연결 끊김")
            self._buf += ch

    def _frame(self):
        """완전한 프레임 하나를 버퍼에서 꺼냄 → (fin, opcode, payload)"""
        self._fill(2)
        b1, b2 = self._buf[0], self._buf[1]
        n, off = b2 & 0x7F, 2
        if n == 126:
            self._fill(4); n, off = struct.unpack(">H", self._buf[2:4])[0], 4
        elif n == 127:
            self._fill(10); n, off = struct.unpack(">Q", self._buf[2:10])[0], 10
        masked = b2 & 0x80
        total = off + (4 if masked else 0) + n
        self._fill(total)
        mask = self._buf[off:off + 4] if masked else None
        data = self._buf[total - n:total]
        self._buf = self._buf[total:]
        if mask:
            data = bytes(x ^ mask[i % 4] for i, x in enumerate(data))
        return b1 & 0x80, b1 & 0x0F, data

    def recv(self) -> str | None:
        """텍스트 메시지 하나. socket.timeout 은 그대로 올려 보냄(호출한 쪽이 주기 작업용으로 씀). 서버 close → WSError"""
        while True:
            fin, op, data = self._frame()
            if op == 0x9:                       # ping → pong
                self._send(0xA, data); continue
            if op == 0xA:
                continue
            if op == 0x8:
                self.closed = True
                raise WSError("서버가 연결을 닫음")
            if op in (0x1, 0x2):
                self._op, self._parts = op, [data]
            elif op == 0x0:
                self._parts.append(data)
            if fin:
                msg = b"".join(self._parts)
                return msg.decode(errors="replace") if self._op == 0x1 else None

    def settimeout(self, t):
        self.sock.settimeout(t)
