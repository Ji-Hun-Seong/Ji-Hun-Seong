"""ob_stream.py — 실시간 호가·체결 허브
토스 웹소켓(wss://openapi-ws.tossinvest.com/ws/v1) 연결 1개로, 지금 화면에서 보고 있는 종목만 구독
  - 계정당 동시 연결 2개 한도 → 대시보드는 1개만 씀
  - 구독 선언은 '현재 전체 목록'을 통째로 보냄(full-replace), 초당 5회 한도 → 바뀔 때만, 0.3초 간격
  - 클라이언트가 180초 조용하면 서버가 끊음 → 50초마다 PING
  - 웹소켓이 안 되면(허용 IP·토큰·네트워크) REST 호가를 0.35초마다 조회하는 방식으로 자동 전환
브라우저로는 dashboard 의 /api/ob-stream (Server-Sent Events) 로 밀어 줌
"""
from __future__ import annotations

import json
import socket
import threading
import time

WS_URL = "wss://openapi-ws.tossinvest.com/ws/v1"
WANT_TTL = 20          # 이 시간 안에 화면이 다시 요청하지 않으면 구독 해제
MAX_CODES = 40         # 종목 × 2채널(호가·체결) ≤ 연결당 100


class Hub:
    def __init__(self):
        self.cv = threading.Condition()
        self.want = {}           # code → 마지막 요청 시각
        self.data = {}           # code → {"ob": 정규화 호가, "last": 체결가, "ts": 시각, "v": 버전}
        self.mode, self.err = "idle", ""
        self._t = None

    # ── 화면 쪽 ──
    def touch(self, code: str):
        with self.cv:
            self.want[code] = time.time()
            if len(self.want) > MAX_CODES:
                for c, _ in sorted(self.want.items(), key=lambda x: x[1])[:len(self.want) - MAX_CODES]:
                    self.want.pop(c, None)
        if not self._t or not self._t.is_alive():
            self._t = threading.Thread(target=self._run, daemon=True, name="ob-hub")
            self._t.start()

    def wait(self, code: str, ver: int, timeout: float):
        """code 의 버전이 ver 보다 새로워질 때까지 기다림 → (버전, 값)"""
        end = time.time() + timeout
        with self.cv:
            while (self.data.get(code) or {}).get("v", 0) <= ver:
                left = end - time.time()
                if left <= 0:
                    break
                self.cv.wait(left)
            x = self.data.get(code) or {}
            return x.get("v", 0), dict(x)

    def _wanted(self):
        now = time.time()
        with self.cv:
            for c in [c for c, t in self.want.items() if now - t > WANT_TTL]:
                self.want.pop(c, None)
            return sorted(self.want)

    def _put(self, code, **kw):
        with self.cv:
            x = self.data.setdefault(code, {"v": 0})
            x.update(kw)
            x["v"] += 1
            x["at"] = time.time()
            self.cv.notify_all()

    # ── 연결 쪽 ──
    def _run(self):
        import manual_trade as mt
        from ws_min import WS, WSError
        fails = 0
        while True:
            codes = self._wanted()
            if not codes:
                self.mode = "idle"
                time.sleep(0.5)
                if not self._wanted():
                    time.sleep(1)
                    continue
            if fails >= 3:                                  # 웹소켓이 계속 안 되면 1분간 REST 로
                self._rest_loop(mt, 60)
                fails = 1
                continue
            ws = None
            try:
                tok = mt.api().token()
                ws = WS(WS_URL, {"Authorization": f"Bearer {tok}"}, timeout=10)
                ws.settimeout(1.0)
                self.mode, self.err, fails = "ws", "", 0
                declared, last_decl, last_ping = None, 0, time.time()
                idle_since = None
                while True:
                    codes = self._wanted()
                    if not codes:
                        idle_since = idle_since or time.time()
                        if time.time() - idle_since > 60:      # 1분 아무도 안 보면 연결 정리
                            break
                    else:
                        idle_since = None
                    if codes != declared and time.time() - last_decl > 0.3:
                        decl = []
                        for mk in ("kr", "us"):
                            cs = [c for c in codes if (c.isdigit() if mk == "kr" else not c.isdigit())]
                            if cs:
                                decl += [{"type": f"orderbook:{mk}", "codes": cs}, {"type": f"trade:{mk}", "codes": cs}]
                        ws.send_text(json.dumps(decl))
                        declared, last_decl = codes, time.time()
                    if time.time() - last_ping > 50:
                        ws.send_text("PING"); last_ping = time.time()
                    try:
                        msg = ws.recv()
                    except socket.timeout:
                        continue
                    if not msg:
                        continue
                    try:
                        j = json.loads(msg)
                    except ValueError:
                        continue
                    if not isinstance(j, dict):
                        continue
                    if j.get("type") == "error":
                        code = (j.get("error") or {}).get("code")
                        self.err = code or "error"
                        if code == "server-shutdown":
                            break
                        if code == "rate-limit-exceeded":
                            time.sleep(1); declared = None
                        continue
                    if j.get("type") != "message":
                        continue
                    topic, d = j.get("topic") or "", j.get("data") or {}
                    parts = topic.split(":")
                    if len(parts) != 3:
                        continue
                    ch, _, sym = parts
                    if ch == "orderbook":
                        self._put(sym, ob=mt.norm_ob(d), src="ws")
                    elif ch == "trade":
                        try:
                            tk = {"p": float(d.get("price")), "v": float(d.get("volume") or 0), "t": d.get("timestamp")}
                        except (TypeError, ValueError):
                            continue
                        with self.cv:
                            cur = self.data.get(sym) or {}
                            ticks = cur.get("ticks") or []
                            ob = cur.get("ob") or {}
                            ask0 = ob["asks"][-1]["p"] if ob.get("asks") else None
                            bid0 = ob["bids"][0]["p"] if ob.get("bids") else None
                            prev = cur.get("last")
                            # 매수·매도 체결 추정: 매도1호가 이상에 체결 = 매수 주도, 매수1호가 이하 = 매도 주도, 사이면 직전가와 비교
                            side = ("B" if ask0 and tk["p"] >= ask0 else "S" if bid0 and tk["p"] <= bid0
                                    else "B" if prev and tk["p"] > prev else "S" if prev and tk["p"] < prev else cur.get("lside", "B"))
                            tk["s"] = side
                            bv = (cur.get("buy_v") or 0) + (tk["v"] if side == "B" else 0)
                            sv = (cur.get("sell_v") or 0) + (tk["v"] if side == "S" else 0)
                            hi = max(cur.get("hi") or tk["p"], tk["p"])
                            lo = min(cur.get("lo") or tk["p"], tk["p"])
                        self._put(sym, last=tk["p"], ts=tk["t"], ticks=([tk] + ticks)[:40], src="ws", buy_v=bv, sell_v=sv, lside=side,
                                  hi=hi, lo=lo, vol_add=(cur.get("vol_add") or 0) + tk["v"])
            except (WSError, OSError, Exception) as e:
                fails += 1
                self.mode, self.err = "reconnect", f"{type(e).__name__}: {str(e)[:120]}"
                print("호가 웹소켓:", self.err, flush=True)
                time.sleep(min(30, 2 ** fails))
            finally:
                if ws:
                    ws.close()

    def _rest_loop(self, mt, secs):
        """웹소켓 대신 REST 호가를 0.35초마다 (MARKET_DATA 초당 15회 한도 안)"""
        self.mode = "rest"
        end = time.time() + secs
        while time.time() < end:
            codes = self._wanted()
            if not codes:
                return
            for c in codes[:3]:                                 # 동시에 보는 종목이 많아도 3개까지만 빠르게
                try:
                    ob = mt.api().orderbook(c) or {}
                    self._put(c, ob=mt.norm_ob(ob), src="rest")
                except Exception as e:
                    self.err = f"REST: {str(e)[:100]}"
            time.sleep(0.35)


HUB = Hub()
