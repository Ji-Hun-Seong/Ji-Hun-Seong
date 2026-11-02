"""토스봇 대시보드 — 서버에서 상시 실행(systemd), 폰에서는 Tailscale(비공개 네트워크)로 접속

  .venv/bin/python dashboard.py          # 포트 8080 (DASH_PORT로 변경)
  선택: .env 에 DASH_PASSWORD=... 를 넣으면 접속 시 비밀번호(아이디는 아무거나)를 물어봄

보여주는 것: 운용 모드·긴급정지, 한국/미국 전략 평가·수익 곡선, 보유 종목(토스 실시간가), 시가 예약·매도 예정,
            최근 자사주 공시 감지, 청산 내역, 나스닥 200일선·목표 레버리지, 실제 토스 계좌 잔고
할 수 있는 것: 긴급 정지 켜기/끄기 (실전 전환은 안전을 위해 서버 명령으로만)
"""
import base64, datetime as dt, json, math, os, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bot  # .env 로드, 장부·API 함수 재사용

STATIC = os.path.join(HERE, "static")
_cache, _lock = {}, threading.Lock()
_api = {"a": None}


def cached(key, ttl, fn):
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
    try:
        val = fn()
    except Exception as e:
        val = {"error": f"{type(e).__name__}: {str(e)[:160]}"}
        if hit:                                   # 실패하면 직전 값 유지
            val = {**hit[1], "stale": True} if isinstance(hit[1], dict) else hit[1]
    with _lock:
        _cache[key] = (time.time(), val)
    return val


def api():
    if _api["a"] is None:
        _api["a"] = bot.api()
    return _api["a"]


def f(x):
    try:
        return float(x)
    except Exception:
        return None


def account():
    a = api()
    h = a.holdings() or {}
    items = [{"symbol": i["symbol"], "name": i["name"], "country": i["marketCountry"], "qty": f(i["quantity"]),
              "price": f(i["lastPrice"]), "avg": f(i["averagePurchasePrice"]), "value": f(i["marketValue"]["amount"]),
              "rate": f(i["profitLoss"]["rate"]), "day": f(i["dailyProfitLoss"]["rate"]), "currency": i["currency"]}
             for i in h.get("items", [])]
    mv = h.get("marketValue", {}).get("amount", {})
    out = {"items": items, "value_krw": f(mv.get("krw")), "value_usd": f(mv.get("usd")),
           "rate": f(h.get("profitLoss", {}).get("rate")), "day": f(h.get("dailyProfitLoss", {}).get("rate")),
           "cash_krw": a.buying_power()}
    try:
        out["cash_usd"] = a.buying_power_usd()
    except Exception:
        out["cash_usd"] = None
    return out


def us_signal():
    a = api()
    q = bot.daily(a, "QQQ", 230)
    today = bot.now().date().isoformat()
    closes = [b[4] for b in q if b[0] < today] or [b[4] for b in q]
    if len(closes) < 201:
        return {"error": "QQQ 일봉 부족"}
    ma200 = sum(closes[-200:]) / 200
    rets = [closes[i] / closes[i - 1] - 1 for i in range(len(closes) - 20, len(closes))]
    m = sum(rets) / 20
    vol = math.sqrt(sum((x - m) ** 2 for x in rets) / 19) * math.sqrt(252)
    L = 0.0 if closes[-1] < ma200 else min(2.0, 0.45 / vol)
    return {"qqq": closes[-1], "ma200": ma200, "vol": vol, "lev": L, "weight": L / 3,
            "series": [[b[0], b[4]] for b in q[-120:]], "ma_series": [[q[i][0], sum(b[4] for b in q[i - 199:i + 1]) / 200]
                                                                   for i in range(max(199, len(q) - 120), len(q))]}


def live_prices(syms):
    if not syms:
        return {}
    return {p["symbol"]: f(p["lastPrice"]) for p in api().prices(syms)}


def detections(n=40):
    p = os.path.join(bot.STATE_DIR, "detections.jsonl")
    if not os.path.exists(p):
        return []
    lines = open(p, encoding="utf-8").read().splitlines()[-n:]
    out = []
    for l in reversed(lines):
        try:
            out.append(json.loads(l))
        except Exception:
            pass
    return out


def data():
    s = bot.peek()
    k, u = s["kr"], s["us"]
    syms = list(k["positions"]) + [bot.CFG["us_symbol"]]
    px = cached("px:" + ",".join(sorted(syms)), 20, lambda: live_prices(syms))
    if "error" in px:
        px = {}
    pos = []
    for code, p in k["positions"].items():
        last = px.get(code) or p.get("last") or p["entry"]
        pos.append({"code": code, "name": p["name"], "qty": p["qty"], "entry": p["entry"], "last": last,
                    "rate": last / p["entry"] - 1, "value": last * p["qty"], "days": p.get("days", 0),
                    "date": p["date"], "how": p.get("how"),
                    "sell": next((x["why"] for x in k["sell_next"] if x["code"] == code), None)})
    kr_eq = k["cash"] + sum(x["value"] for x in pos)
    upx = px.get(bot.CFG["us_symbol"])
    us_eq = u["cash"] + u["qty"] * (upx or u.get("avg") or 0)
    cl = k["closed"]
    return {
        "now": bot.now().isoformat(timespec="seconds"), "mode": s["mode"], "created": s["created"],
        "stopped": bot.stopped(),
        "kr": {"capital": bot.CFG["kr_capital"], "cash": k["cash"], "equity": kr_eq, "positions": pos,
               "pending": [{"code": p["code"], "name": p["name"], "qty": p["qty"], "how": p.get("how"), "for": p.get("for"),
                            "detected": p.get("detected")} for p in k["pending"]],
               "curve": k["equity"][-250:], "closed": cl[-60:][::-1], "slots": bot.CFG["kr_slots"],
               "stats": {"n": len(cl), "win": (sum(1 for x in cl if x["ret"] > 0) / len(cl)) if cl else None,
                         "pnl": sum(x["pnl"] for x in cl), "avg": (sum(x["ret"] for x in cl) / len(cl)) if cl else None}},
        "us": {"capital": bot.CFG["us_capital"], "cash": u["cash"], "qty": u["qty"], "avg": u.get("avg"), "price": upx,
               "symbol": bot.CFG["us_symbol"], "equity": us_eq, "curve": u.get("equity", [])[-250:],
               "history": u.get("history", [])[-30:][::-1],
               "signal": cached("us_signal", 600, us_signal)},
        "detections": detections(),
        "account": cached("account", 60, account),
    }


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _auth(self):
        pw = os.environ.get("DASH_PASSWORD")
        if not pw:
            return True
        h = self.headers.get("Authorization", "")
        if h.startswith("Basic "):
            try:
                if base64.b64decode(h[6:]).decode().split(":", 1)[1] == pw:
                    return True
            except Exception:
                pass
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="toss-bot"')
        self.end_headers()
        return False

    def _send(self, code, body, ctype):
        b = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if not self._auth():
            return
        path = self.path.split("?")[0]
        if path == "/api/data":
            try:
                return self._send(200, json.dumps(data(), ensure_ascii=False, default=str), "application/json; charset=utf-8")
            except Exception as e:
                return self._send(500, json.dumps({"error": str(e)}), "application/json")
        name = {"/": "index.html"}.get(path, path.lstrip("/"))
        fp = os.path.normpath(os.path.join(STATIC, name))
        if not fp.startswith(STATIC) or not os.path.isfile(fp):
            return self._send(404, "not found", "text/plain")
        ctype = {".html": "text/html; charset=utf-8", ".json": "application/manifest+json", ".png": "image/png",
                 ".js": "text/javascript"}.get(os.path.splitext(fp)[1], "application/octet-stream")
        self._send(200, open(fp, "rb").read(), ctype)

    def do_POST(self):
        if not self._auth():
            return
        if self.path == "/api/stop":
            n = int(self.headers.get("Content-Length") or 0)
            on = json.loads(self.rfile.read(n) or b"{}").get("on")
            stop = os.path.join(HERE, "STOP")
            if on:
                open(stop, "w").close()
            elif os.path.exists(stop):
                os.remove(stop)
            bot.tg("⛔ 대시보드에서 긴급 정지 켜짐 — 새 주문 중지" if on else "▶️ 대시보드에서 긴급 정지 해제 — 주문 재개")
            return self._send(200, json.dumps({"stopped": bot.stopped()}), "application/json")
        self._send(404, "not found", "text/plain")


if __name__ == "__main__":
    host, port = os.environ.get("DASH_HOST", "0.0.0.0"), int(os.environ.get("DASH_PORT", "8080"))
    print(f"대시보드 http://{host}:{port}", flush=True)
    ThreadingHTTPServer((host, port), H).serve_forever()
