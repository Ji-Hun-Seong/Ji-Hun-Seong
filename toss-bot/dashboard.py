"""토스봇 대시보드 — 서버에서 상시 실행(systemd), 폰에서는 Tailscale(비공개 네트워크)로 접속

  .venv/bin/python dashboard.py          # 포트 8080 (DASH_PORT로 변경)
  차트 탭: 종목 검색 → 볼린저(책 기법)·자사주 공시·외국인 수급 판정 (chartpage/ 모듈, 별도 서버 없음)
  선택: .env 에 DASH_PASSWORD=... 를 넣으면 접속 시 비밀번호(아이디는 아무거나)를 물어봄

보여주는 것: 운용 모드·긴급정지, 한국/미국 전략 평가·수익 곡선, 보유 종목(토스 실시간가), 시가 예약·매도 예정,
            최근 자사주 공시 감지, 청산 내역, 나스닥 200일선·목표 레버리지, 실제 토스 계좌 잔고
할 수 있는 것: 긴급 정지 켜기/끄기 (실전 전환은 안전을 위해 서버 명령으로만)
"""
import base64, datetime as dt, json, math, os, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "chartpage"))
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


# ── 차트 탭: 종목 검색 → 볼린저(책 기법) + 자사주 공시 + 외국인 수급 AND 판정 ─────────────
def chart_search(q):
    import data_sources as ds
    return [{"name": c["name"], "code": c["code"], "us": bool(c.get("us"))} for c in ds.search(q, 8)]


def chart_ohlcv(code, us):
    """토스 일봉(대시보드와 같은 출처) → 실패하면 야후"""
    import pandas as pd
    import data_sources as ds
    try:
        rows = bot.daily(api(), code, 260)
        if len(rows) < 60:
            raise ValueError("일봉 부족")
        df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
        df.index = pd.to_datetime(df.pop("date"))
        return df[~df.index.duplicated(keep="last")], "토스증권"
    except Exception:
        if not us:
            try:
                import stock_info as si
                return si.kr_ohlcv(code), "네이버"
            except Exception:
                pass
        return ds.get_ohlcv(code, us=us, rng="2y"), "야후 파이낸스"


def chart_data(it):
    import data_sources as ds
    from concurrent.futures import ThreadPoolExecutor
    from bb_strategy import Config, add_indicators, evaluate, scan
    us = bool(it.get("us"))
    t0 = time.time()
    safe = lambda fn, default: (lambda: _try(fn, default))
    with ThreadPoolExecutor(3) as ex:                      # 시세·공시·수급을 동시에
        f_px = ex.submit(chart_ohlcv, it["code"], us)
        f_bb = ex.submit(safe(lambda: [] if us else ds.get_buybacks(it.get("corp_code")), []))
        f_fl = ex.submit(safe(lambda: None if us else ds.get_flows(it["code"]), None))
        df, src = f_px.result()
        buybacks, flows = f_bb.result(), f_fl.result()
    t1 = time.time()
    cfg = Config(require=("bollinger",)) if us else Config()
    r = evaluate(df, buybacks, flows, cfg)
    d = add_indicators(df, cfg).join(scan(df, buybacks, flows, cfg, last=120)[["buy", "bollinger_ok"]], how="left").tail(120)
    labels = {"buyback": "자사주 공시", "bollinger": "볼린저", "foreign": "외국인 수급"}
    checks = [{"label": labels[k], "ok": bool(ok),
               "msg": "수급 데이터 없음 (KIS 키 미설정)" if k == "foreign" and flows is None else msg}
              for k, (ok, msg) in r["checks"].items() if k in cfg.require]
    num = lambda s: [None if v != v else round(float(v), 4) for v in s]     # NaN → null
    fl = None
    if flows is not None and not flows.empty:
        fl = num(flows["frgn_eok"].reindex(d.index))
    last, prev = d.iloc[-1], d.iloc[-2]
    return {"name": it["name"], "code": it["code"], "us": us, "src": src, "asof": f"{d.index[-1]:%Y-%m-%d}",
            "close": float(last["close"]), "chg": float(last["close"] / prev["close"] - 1),
            "pctb": float(last["pctb"]), "bw": float(last["bw"]), "mfi": float(last["mfi"]),
            "buy": bool(r["buy"]), "checks": checks,
            "dates": [f"{t:%m-%d}" for t in d.index], "closeS": num(d["close"]), "upper": num(d["upper"]),
            "mid": num(d["mid"]), "lower": num(d["lower"]), "pctbS": num(d["pctb"]), "bwS": num(d["bw"]),
            "buyS": [bool(x) if x == x else False for x in d["buy"]],
            "bbS": [bool(x) if x == x else False for x in d["bollinger_ok"]],
            "flows": fl, "buybacks": sorted(buybacks, key=lambda e: e["date"], reverse=True)[:8],
            "buyback_marks": [e["date"][5:10] for e in buybacks],
            "timing": {"data": round(t1 - t0, 2), "calc": round(time.time() - t1, 2)}}


def _try(fn, default):
    try:
        return fn()
    except Exception:
        return default


def chart_ttl():
    """장중(평일 09:00~15:40)엔 10분, 그 외엔 데이터가 안 바뀌므로 6시간"""
    n = bot.now()
    return 600 if n.weekday() < 5 and (9, 0) <= (n.hour, n.minute) <= (15, 40) else 6 * 3600


def chart_lookup(q):
    import data_sources as ds
    hits = ds.search(q, 1)
    if not hits:
        return {"error": f"'{q}' 종목을 찾지 못했습니다"}
    it = hits[0]
    key = "chart:" + it["code"]
    out = cached(key, chart_ttl(), lambda: chart_data(it))
    if isinstance(out, dict) and out.get("error") and not out.get("stale"):
        with _lock:
            _cache.pop(key, None)                 # 실패는 캐시하지 않음 → 다음 검색 때 다시 시도
    return out


def warm_up():
    """대시보드 시작 시 종목 목록을 미리 받아 둠 → 첫 검색이 느리지 않게"""
    try:
        import data_sources as ds
        ds.load_corps()
    except Exception as e:
        print("종목 목록 준비 실패:", e, flush=True)
    for k in PICKS:                               # 발굴 목록도 미리 (종목 상세의 '어느 목록' 표시에 씀)
        picks(k)


# ── 감시 탭: scanner.py 가 쓰는 state/scanner/{kr|us}-날짜.json 을 읽어 보여 줌 ─────────────
def scan_data(mkt):
    import glob
    mkt = "us" if mkt == "us" else "kr"
    files = sorted(glob.glob(os.path.join(bot.STATE_DIR, "scanner", f"{mkt}-*.json")))
    if not files:
        return {"market": mkt, "empty": True}
    s = json.load(open(files[-1], encoding="utf-8"))
    rows = [{"code": c, **v} for c, v in s["stocks"].items()
            if v.get("in_list", True) and not v.get("pref") and (v.get("chg") or 0) >= 5]
    rows.sort(key=lambda r: -(r.get("chg") or 0))
    return {"market": mkt, "day": s["day"], "updated": s.get("updated"), "polls": s.get("polls"),
            "running": time.time() - os.path.getmtime(files[-1]) < 180, "rows": rows[:40],
            "events": s.get("events", [])[-60:][::-1],
            "counts": {"ge10": sum(1 for v in s["stocks"].values() if (v.get("max_chg") or 0) >= 10 and not v.get("pref")),
                       "limit": sum(1 for v in s["stocks"].values() if v.get("limit_up_at") and not v.get("pref"))}}


# ── 발굴 탭: 급등 후보 · 가치주 20선 · 애크먼 TOP10 ─────────────────────────────
#   데이터는 GitHub(Actions가 매일·매주 갱신)에서 직접 받아 옴 → 서버에서 git pull 안 해도 최신.
#   GitHub에 못 가면 서버에 있는 저장소 파일을 씀.
REPO = os.path.dirname(HERE)
GH_RAW = "https://raw.githubusercontent.com/Ji-Hun-Seong/Ji-Hun-Seong"


def gh_text(path, branch="main", ttl=1800):
    def fetch():
        import requests
        r = requests.get(f"{GH_RAW}/{branch}/{path}", timeout=10)
        r.raise_for_status()
        return {"text": r.text, "src": "github"}
    out = cached(f"gh:{branch}:{path}", ttl, fetch)
    if isinstance(out, dict) and "text" in out:
        return out["text"]
    local = os.path.join(REPO, path)
    if branch == "main" and os.path.exists(local):
        return open(local, encoding="utf-8").read()
    raise FileNotFoundError(f"{path} 를 GitHub·서버 어디서도 못 찾음 ({out.get('error') if isinstance(out, dict) else ''})")


def picks_surge():
    j = json.loads(gh_text("surge-study/data/candidates/latest.json", ttl=900))
    return {"kind": "surge", "date": j["date"], "method": j.get("method"), "n_scored": j.get("n_scored"),
            "items": [{"rank": i, **c} for i, c in enumerate(j["candidates"][:10], 1)],
            "more": j["candidates"][10:20], "prev": j.get("prev")}


def picks_value():
    import tempfile
    vb = os.path.join(REPO, "value-bot")
    if vb not in sys.path:
        sys.path.insert(0, vb)
    import recommend
    from value_dna import load_profile
    tmp = tempfile.mkdtemp(prefix="vb-")
    for fn in ("universe.csv", "profile.json", "holdings.txt", "recent_buys.txt", "DATA_ASOF"):
        try:
            open(os.path.join(tmp, fn), "w", encoding="utf-8").write(gh_text(f"value-bot/{fn}", ttl=3600))
        except Exception:
            pass
    dna = load_profile(os.path.join(tmp, "profile.json"))
    hf = os.path.join(tmp, "holdings.txt")
    if os.path.exists(hf):
        real = [l.strip() for l in open(hf, encoding="utf-8") if l.strip() and not l.startswith("#")]
        if real:
            dna.holdings = real
    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()):
        recommend.apply_recent_buys(dna, os.path.join(tmp, "recent_buys.txt"))
        picked, _ = recommend.rank(dna, recommend.load_universe(os.path.join(tmp, "universe.csv")))
    asof = open(os.path.join(tmp, "DATA_ASOF")).read().strip() if os.path.exists(os.path.join(tmp, "DATA_ASOF")) else ""
    held = set(dna.holdings)
    items = []
    for i, c in enumerate(picked[:20], 1):
        r = c.row
        items.append({"rank": i, "name": c.name, "code": r["ticker"], "total": round(c.total, 1),
                      "scores": {k: round(v) for k, v in c.scores.items()}, "penalty": c.penalty,
                      "reasons": c.reasons, "risks": c.risks, "held": c.name in held, "sector": r.get("sector"),
                      "group": r.get("group"), "pbr": recommend.num(r.get("pbr")), "per": recommend.num(r.get("per")),
                      "yield": recommend.num(r.get("yield_pct")), "note": r.get("note")})
    return {"kind": "value", "asof": asof, "items": items}


def picks_ackman():
    j = json.loads(gh_text("weekly_state.json", branch="ackman-weekly", ttl=3600))
    b = j.get("board")
    if b:
        return {"kind": "ackman", "week": b["week"], "asof": b["asof"], "last_13f": b.get("last_13f"),
                "items": b["items"][:10], "more": b["items"][10:20]}
    # 대시보드 기능 추가 전 저장본: 순위·편입가만 있음
    ranks, base = j.get("ranks", {}), j.get("baseline", {})
    items = [{"rank": n, "t": t, "name": t, "price": (base.get(t) or {}).get("price"), "since": (base.get(t) or {}).get("date")}
             for t, n in sorted(ranks.items(), key=lambda x: x[1])]
    return {"kind": "ackman", "week": j.get("sent_week"), "asof": None, "items": items, "partial": True}


PICKS = {"surge": (picks_surge, 900), "value": (picks_value, 3600), "ackman": (picks_ackman, 3600)}


def picks(kind):
    fn, ttl = PICKS.get(kind, PICKS["surge"])
    return cached("picks:" + kind, ttl, fn)


# ── 종목 상세: 시세·이평선·볼린저·수급·재무·공시·밸류를 한 번에 ─────────────────────
def stock_detail(q, us_hint=None):
    import data_sources as ds
    import stock_info as si
    q = q.strip()
    hits = ds.search(q, 1)
    if not hits:
        return {"error": f"'{q}' 종목을 찾지 못했습니다"}
    it = hits[0]
    if us_hint and not it.get("us"):
        it = {"name": q.upper(), "code": q.upper(), "us": True}
    key = "stock:" + it["code"]

    def us_px(sym):
        df, _ = chart_ohlcv(sym, True)
        return df
    out = cached(key, chart_ttl(), lambda: si.detail(it, us_px))
    if isinstance(out, dict) and out.get("error") and not out.get("stale"):
        with _lock:
            _cache.pop(key, None)
        return out
    # 어느 목록에 들어 있는지 표시 (보유·후보·20선·애크먼)
    tags = []
    try:
        s = bot.peek()
        if it["code"] in s["kr"]["positions"]:
            tags.append("🤖 봇 보유")
    except Exception:
        pass
    for kind, label in (("surge", "🚀 급등 후보"), ("value", "💎 가치주"), ("ackman", "🇺🇸 애크먼")):
        p = _cache.get("picks:" + kind)
        if p and isinstance(p[1], dict):
            for x in p[1].get("items", []):
                if (x.get("code") or x.get("t")) == it["code"]:
                    tags.append(f"{label} {x.get('rank') or ''}{'위' if x.get('rank') else ''}".strip())
                    if kind == "value" and x.get("held"):
                        tags.append("📌 내 계좌 보유")
    return {**out, "tags": tags}


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
        gz = len(b) > 2048 and "gzip" in (self.headers.get("Accept-Encoding") or "") and not ctype.startswith("image/")
        if gz:                                    # 전체 기간 차트 데이터(수백 KB) → 보통 1/4 크기로
            import gzip
            b = gzip.compress(b, 5)
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        if gz:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if not self._auth():
            return
        path = self.path.split("?")[0]
        if path == "/api/scan":
            m = (parse_qs(urlparse(self.path).query).get("m") or ["kr"])[0]
            try:
                return self._send(200, json.dumps(scan_data(m), ensure_ascii=False, default=str), "application/json; charset=utf-8")
            except Exception as e:
                return self._send(200, json.dumps({"error": str(e)[:200]}, ensure_ascii=False), "application/json; charset=utf-8")
        if path in ("/api/picks", "/api/stock"):
            qs = parse_qs(urlparse(self.path).query)
            try:
                if path == "/api/picks":
                    out = picks((qs.get("k") or ["surge"])[0])
                else:
                    out = stock_detail((qs.get("q") or [""])[0], (qs.get("us") or [""])[0] == "1")
            except Exception as e:
                out = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
            return self._send(200, json.dumps(out, ensure_ascii=False, default=str), "application/json; charset=utf-8")
        if path in ("/api/search", "/api/chart"):
            q = (parse_qs(urlparse(self.path).query).get("q") or [""])[0].strip()
            try:
                if path == "/api/search":
                    out = chart_search(q) if q else []
                else:
                    out = chart_lookup(q) if q else {"error": "종목을 입력하세요"}
                return self._send(200, json.dumps(out, ensure_ascii=False, default=str), "application/json; charset=utf-8")
            except Exception as e:
                return self._send(200, json.dumps({"error": f"{type(e).__name__}: {str(e)[:200]}"}, ensure_ascii=False),
                                  "application/json; charset=utf-8")
        if path == "/api/doc":                    # 공시·리포트 상세 (앱 안에서 보기)
            qs = parse_qs(urlparse(self.path).query)
            k, i = (qs.get("k") or [""])[0], (qs.get("id") or [""])[0]
            try:
                import doc_detail
                out = cached(f"doc:{k}:{i}", 6 * 3600, lambda: doc_detail.detail(k, i))
                if out.get("error"):              # 실패는 캐시하지 않음 → 다음에 다시 시도
                    with _lock:
                        _cache.pop(f"doc:{k}:{i}", None)
            except Exception as e:
                out = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
            return self._send(200, json.dumps(out, ensure_ascii=False, default=str), "application/json; charset=utf-8")
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
    threading.Thread(target=warm_up, daemon=True).start()
    ThreadingHTTPServer((host, port), H).serve_forever()
