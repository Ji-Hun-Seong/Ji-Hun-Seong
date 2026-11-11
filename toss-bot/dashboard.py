"""토스봇 대시보드 — 서버에서 상시 실행(systemd), 폰에서는 Tailscale(비공개 네트워크)로 접속

  .venv/bin/python dashboard.py          # 포트 8080 (DASH_PORT로 변경)
  차트 탭: 종목 검색 → 볼린저(책 기법)·자사주 공시·외국인 수급 판정 (chartpage/ 모듈, 별도 서버 없음)
  선택: .env 에 DASH_PASSWORD=... 를 넣으면 접속 시 비밀번호(아이디는 아무거나)를 물어봄

투자 원칙: 장기 9 : 단기 1 (단기는 최대 2) — 홈 '장기·단기 비율' 카드, 발굴 '🏛️ 대가' 목록, 종목 상세 '대가 체크'
            (가치 5인 버핏·그레이엄·멍거·애크먼·클라만 + 성장 5인 린치·피셔·드러켄밀러·템플턴·로 프라이스, chartpage/heroes.py)
보여주는 것: 운용 모드·긴급정지, 한국/미국 전략 평가·수익 곡선, 보유 종목(토스 실시간가), 시가 예약·매도 예정,
            최근 자사주 공시 감지, 청산 내역, 나스닥 200일선·목표 레버리지, 실제 토스 계좌 잔고
할 수 있는 것: 긴급 정지 켜기/끄기 (실전 전환은 안전을 위해 서버 명령으로만)
"""
import base64, csv, datetime as dt, io, json, math, os, re, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "chartpage"))
import bot  # .env 로드, 장부·API 함수 재사용

STATIC = os.path.join(HERE, "static")
_cache, _lock = {}, threading.Lock()
_api = {"a": None}


# ── 보기 전용(조회만) — Tailscale '기기 공유'로 들어온 다른 사람(예: 아빠)은 자동으로 보기 전용 ─────
#   서버 주인과 같은 Tailscale 계정의 기기 = 주인(전부), 다른 계정 = 보기 전용(계좌 금액·긴급 정지 숨김)
#   .env  DASH_OWNERS=내메일@gmail.com   (서버가 태그로 등록돼 주인 판별이 안 될 때만)
#         DASH_VIEWERS=아빠메일@gmail.com (같은 계정이라도 보기 전용으로 둘 사람)
_roles = {}


def _ts_json(*args):
    import subprocess
    r = subprocess.run(["tailscale", *args, "--json"], capture_output=True, text=True, timeout=4)
    return json.loads(r.stdout)


def role_of(ip: str) -> str:
    return role_info(ip)[0]


def role_info(ip: str) -> tuple[str, str]:
    """(역할, 이유) — 같은 Tailscale 계정 기기면 owner, 다른 계정(공유받은 사람)이면 viewer"""
    if not ip.startswith("100."):                 # 서버 자신(localhost) 등 → 주인
        return "owner", "로컬 접속"
    hit = _roles.get(ip)
    if hit and time.time() - hit[0] < 600:
        return hit[1], hit[2]
    lst = lambda k: {x.strip().lower() for x in os.environ.get(k, "").split(",") if x.strip()}
    role, why = "viewer", ""
    try:
        st = _ts_json("status")
        me = (st.get("Self") or {}).get("UserID")
        users = st.get("User") or {}
        peer = next((p for p in (st.get("Peer") or {}).values() if ip in (p.get("TailscaleIPs") or [])), None)
        uid = peer.get("UserID") if peer else None
        login = ((users.get(str(uid)) or {}).get("LoginName") or "").lower() if uid is not None else ""
        if peer is None:                          # 상태 목록에 없으면 whois로 한 번 더
            w = _ts_json("whois", ip)
            uid = (w.get("UserProfile") or {}).get("ID")
            login = ((w.get("UserProfile") or {}).get("LoginName") or "").lower()
        if login and login in lst("DASH_VIEWERS"):
            role, why = "viewer", f"{login} = DASH_VIEWERS"
        elif login and login in lst("DASH_OWNERS"):
            role, why = "owner", f"{login} = DASH_OWNERS"
        elif uid is not None and uid == me:
            role, why = "owner", "서버와 같은 Tailscale 계정"
        else:
            role, why = "viewer", f"다른 계정({login or uid})"
    except Exception as e:                        # 판별 실패 → 안전하게 보기 전용
        role, why = "viewer", f"계정 확인 실패: {type(e).__name__}: {str(e)[:80]}"
        print("tailscale 역할 판별 실패:", e, flush=True)
    _roles[ip] = (time.time(), role, why)
    return role, why


def for_viewer(d: dict) -> dict:
    """보기 전용: 실제 계좌 금액·장기/단기 금액 비율을 빼고 긴급 정지는 못 쓰게"""
    return {**d, "account": {"hidden": True}, "mix": {"hidden": True}, "viewer": True}


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


_gzc = {}                                         # 정적 파일 압축본 (경로+ETag → gzip 바이트)
_bg = {}                                          # 키 → 계산 시작 시각 (같은 계산이 겹쳐 돌지 않게)


def swr(key, ttl, fn):
    """⚡ 오래된 값이라도 있으면 바로 돌려주고, 기한이 지났으면 뒤에서 한 번만 새로 계산 (stale-while-revalidate).
       처음(값이 아예 없을 때)만 기다림. → 발굴·계좌 화면이 15분마다 한 번씩 '한세월' 걸리던 문제"""
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
        running = _bg.get(key)
        if hit and not (running and time.time() - running < 600):
            _bg[key] = time.time()

            def work():
                try:
                    val = fn()
                except Exception as e:
                    val = {**hit[1], "stale": True} if isinstance(hit[1], dict) else hit[1]
                    print(f"swr {key} 실패: {type(e).__name__} {str(e)[:120]}", flush=True)
                with _lock:
                    _cache[key] = (time.time(), val)
                    _bg.pop(key, None)
            threading.Thread(target=work, daemon=True).start()
    if hit:
        return hit[1]
    return cached(key, ttl, fn)


def bg_cached(key, ttl, fn):
    """무거운 계산은 뒤에서 — 화면은 기다리지 않고 직전 결과를 바로 받음(없으면 {"loading": ...}).
       기한이 지나면 뒤에서 한 번만 새로 계산 (뉴스·공시 레이더: 처음 1~2분 걸려서 화면이 '불러오는 중'에 멈추던 문제)"""
    with _lock:
        hit = _cache.get(key)
        running = _bg.get(key)
        fresh = hit and time.time() - hit[0] < ttl
        if not fresh and not (running and time.time() - running < 600):
            _bg[key] = time.time()

            def work():
                try:
                    val = fn()
                except Exception as e:
                    val = {"error": f"{type(e).__name__}: {str(e)[:160]}"}
                    if hit and isinstance(hit[1], dict) and not hit[1].get("error"):
                        val = {**hit[1], "stale": True}
                with _lock:
                    _cache[key] = (time.time(), val)
                    _bg.pop(key, None)
            threading.Thread(target=work, daemon=True).start()
            running = _bg[key]
    if hit:
        return {**hit[1], "refreshing": bool(running)} if isinstance(hit[1], dict) else hit[1]
    return {"loading": True, "since": int(time.time() - (running or time.time()))}


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
    px = swr("px:" + ",".join(sorted(syms)), 20, lambda: live_prices(syms))
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
               "signal": swr("us_signal", 600, us_signal)},
        "detections": detections(),
        "account": cached("account", 60, account),
        "mix": _try(lambda: mix(s["mode"], pos, kr_eq, us_eq, u["qty"], upx), {"error": "비율 계산 실패"}),
    }


# ── 장기 9 : 단기 1 — 내 돈이 어디에 얼마나 있나 ─────────────────────────────
#   단기 = 봇 운용금(한국 자사주 스윙 + 미국 TQQQ 레버리지, 봇 현금 포함)
#   장기 = 실제 계좌 주식 평가액 − (실전 모드일 때) 봇이 산 종목
def usdkrw():
    def fetch():
        if os.environ.get("USDKRW"):
            return {"fx": float(os.environ["USDKRW"]), "src": ".env"}
        import data_sources as ds
        df = ds._yahoo("KRW=X", "3mo")
        return {"fx": float(df["close"].iloc[-1]), "src": "야후"}
    out = cached("usdkrw", 6 * 3600, fetch)
    return out.get("fx") or 1400.0


def mix(mode, pos, kr_eq, us_eq, us_qty, us_px):
    import heroes
    P = heroes.PRINCIPLES["mix"]
    fx = usdkrw()
    short = kr_eq + us_eq * fx
    limit = bot.CFG["kr_capital"] + bot.CFG["us_capital"] * fx
    acct = cached("account", 60, account)
    out = {"target": P["target_short"], "max": P["max_short"], "text": P["text"], "fx": fx, "mode": mode,
           "short": short, "short_kr": kr_eq, "short_us": us_eq * fx, "limit": limit}
    if not isinstance(acct, dict) or not acct.get("items"):
        out["error"] = (acct or {}).get("error") if isinstance(acct, dict) and acct.get("error") else "계좌 보유 종목이 없어 장기 금액을 알 수 없음"
        return out
    bot_codes = {c for c in (pos and [p["code"] for p in pos] or [])}
    longs = []
    for i in acct["items"]:
        v = (i.get("value") or 0) * (fx if i.get("currency") == "USD" else 1)
        code = re.sub(r"\D", "", str(i.get("symbol") or ""))[-6:]
        if mode == "live" and (code in bot_codes or i.get("symbol") == bot.CFG["us_symbol"]):
            continue                              # 실전 모드: 봇이 산 종목은 단기 쪽에 이미 들어 있음
        longs.append({"name": i.get("name"), "code": code if i.get("currency") != "USD" else i.get("symbol"),
                      "us": i.get("currency") == "USD", "value": v})
    long_v = sum(x["value"] for x in longs)
    tot = long_v + short
    share = short / tot if tot else None
    lim_share = limit / (long_v + limit) if (long_v + limit) else None
    longs.sort(key=lambda x: -x["value"])
    for x in longs:
        x["w"] = x["value"] / long_v if long_v else None
    # 장기 보유 종목의 대가 등급 (발굴 '대가' 목록이 계산돼 있으면)
    hp = _cache.get("picks:hero")
    gmap = {x["code"]: x["grade"] for x in (hp[1].get("items", []) if hp and isinstance(hp[1], dict) else [])}
    for x in longs:
        if x["code"] in gmap:
            x["grade"] = gmap[x["code"]]
    status = "ok" if share is not None and share <= P["target_short"] + 0.005 else "warn" if share is not None and share <= P["max_short"] else "bad"
    out.update({"long": long_v, "share": share, "limit_share": lim_share, "status": status, "longs": longs,
                "n_long": len(longs), "over15": [x["name"] for x in longs if (x["w"] or 0) > 0.15]})
    return out


# ── 차트 탭: 종목 검색 → 볼린저(책 기법) + 자사주 공시 + 외국인 수급 AND 판정 ─────────────
def chart_search(q):
    import data_sources as ds
    return [{"name": c["name"], "code": c["code"], "us": bool(c.get("us")), "mkt": c.get("mkt") or ("🇰🇷 한국" if not c.get("us") else None),
             "exch": c.get("exch")} for c in ds.search(q, 8)]


def toss_popular(tag):
    """🔥 토스증권 '인기' TOP 10 — 토스증권 웹 홈 화면이 쓰는 비공식 조회 주소(로그인·키 안 씀), 공식 Open API엔 순위가 없음
       인기(전체를 받아 국내/해외로 나눔) → 안 되면 토스 거래대금. 둘 다 안 되면 화면에서 카드를 숨김"""
    import requests

    def fetch(rid, t):
        r = requests.post("https://wts-cert-api.tossinvest.com/api/v2/dashboard/wts/overview/ranking", timeout=8,
                          json={"id": rid, "tag": t, "duration": "realtime", "filters": []},
                          headers={"Accept": "application/json", "Origin": "https://www.tossinvest.com", "Referer": "https://www.tossinvest.com/",
                                   "User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        return (r.json().get("result") or {}).get("products") or []

    is_kr = lambda p: len(str(p.get("productCode") or p.get("code") or "")) == 7 and str(p.get("productCode") or p.get("code"))[0] == "A"
    title, rows = "인기", []
    try:
        rows = [p for p in fetch("realtime_stock", "all") if is_kr(p) == (tag == "kr")]
    except Exception:
        pass
    if len(rows) < 5:
        title, rows = "거래대금", fetch("biggest_total_amount", tag)
    first = lambda d, *ks: next((d[k] for k in ks if isinstance(d, dict) and d.get(k) not in (None, "")), None)
    items = []
    for it in rows[:10]:
        p = it["price"] if isinstance(it.get("price"), dict) else it
        code = str(first(it, "productCode", "code") or "")
        name = first(it, "name", "productName", "stockName") or code
        sym = first(it, "symbol", "ticker")
        close, base = first(p, "close"), first(p, "base")
        krw, base_krw = first(p, "closeKrw"), first(p, "baseKrw")
        a, b = (krw, base_krw) if krw and base_krw else (close, base)
        us = tag == "us"
        items.append({"name": name, "code": (sym or name) if us else (code[1:] if code[:1] == "A" else code), "us": us,
                      "krw": krw if us else close, "usd": close if us else None,
                      "chg": round((a / b - 1) * 100, 2) if a and b else None})
    if not items:
        raise ValueError("토스 응답에 종목이 없어요")
    return {"tag": tag, "title": title, "items": items, "at": time.strftime("%H:%M")}


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


def mini_chart(q, us_hint=False):
    """🖱️ 마우스 올렸을 때 미니 차트용 — 최근 3개월 종가만 (가볍게, 서버 캐시)"""
    import data_sources as ds
    q = (q or "").strip()
    if not q:
        return {"error": "종목 없음"}
    hits = ds.search(q, 1)
    it = hits[0] if hits else None
    if us_hint and (not it or not it.get("us")):
        it = {"name": q.upper(), "code": q.upper(), "us": True}
    if not it:
        return {"error": f"'{q}' 종목을 찾지 못했습니다"}

    def build():
        df, _ = chart_ohlcv(it["code"], bool(it.get("us")))
        c = df["close"].tail(64)
        return {"name": it["name"], "code": it["code"], "us": bool(it.get("us")), "asof": f"{c.index[-1]:%m-%d}",
                "close": float(c.iloc[-1]), "chg": float(c.iloc[-1] / c.iloc[-2] - 1),
                "closes": [round(float(v), 4) for v in c]}
    key = "mini:" + it["code"]
    out = cached(key, min(chart_ttl(), 300), build)
    if isinstance(out, dict) and out.get("error") and not out.get("stale"):
        with _lock:
            _cache.pop(key, None)
    return out


def warm_up():
    """대시보드 시작 시 종목 목록을 미리 받아 둠 → 첫 검색이 느리지 않게"""
    try:
        import data_sources as ds
        ds.load_corps()
    except Exception as e:
        print("종목 목록 준비 실패:", e, flush=True)
    from concurrent.futures import ThreadPoolExecutor
    ks = ("surge", "hero", "fund", "value", "ackman", "hero_us", "etf")
    with ThreadPoolExecutor(4) as ex:               # 발굴 목록을 동시에 미리 (하나가 느려도 나머지는 먼저 준비)
        list(ex.map(lambda k: _safe_pick(k), ks))
    while True:                                     # ⚡ 계속 데워 둠 — 기한 지난 목록은 뒤에서 새로 (화면은 기다리지 않음)
        time.sleep(120)
        for k in ks:
            _safe_pick(k)
        try:
            data()
        except Exception:
            pass


def _safe_pick(k):
    try:
        picks(k)
    except Exception as e:
        print(f"미리 받기 실패 {k}: {e}", flush=True)


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


# ── 감시 탭: 📰 뉴스·공시 레이더 — 재료는 나왔는데 주가는 아직 덜 움직인 종목 ─────────────
_news_cache = {}


def _news(name, n=8):
    """구글 뉴스 최근 2일 제목 (종목명 기준) — 15분 캐시"""
    hit = _news_cache.get(name)
    if hit and time.time() - hit[0] < 900:
        return hit[1]
    sp = os.path.join(REPO, "surge-study")
    if sp not in sys.path:
        sys.path.insert(0, sp)
    import collect
    nw = collect.news(name, n)
    _news_cache[name] = (time.time(), nw)
    return nw


def _dart_list(day):
    """그날 전체 공시 목록(코스피·코스닥만) — OpenDART list.json"""
    key = os.environ.get("DART_API_KEY") or os.environ.get("DART_KEY")
    if not key:
        raise RuntimeError("서버 .env 에 DART_API_KEY 가 없음")
    import requests
    out, page = [], 1
    while page <= 20:
        j = requests.get("https://opendart.fss.or.kr/api/list.json", timeout=20,
                         params={"crtfc_key": key, "bgn_de": day, "end_de": day, "page_no": page, "page_count": 100}).json()
        if j.get("status") not in ("000",):
            if j.get("status") == "013":                  # 조회된 데이터 없음
                break
            raise RuntimeError(f"DART {j.get('status')}: {j.get('message')}")
        out += [x for x in j.get("list") or [] if x.get("corp_cls") in ("Y", "K") and x.get("stock_code")]
        if page >= int(j.get("total_page") or 1):
            break
        page += 1
    return out


# ── 재료 순위: 같은 '공급계약'이라도 크기·신선도·덩치·반영 정도가 다름 → 100점 만점으로 줄 세움 ──
#   종류(0~30) + 크기(0~30) + 신선도(-20~+10) + 덩치(-15~+5) + 덜 오름(0~10) + 관심(0~15) − 악재
GRADES = [(70, "S", "지금 먼저 보기"), (55, "A", "오늘 확인"), (40, "B", "시간 나면"), (-999, "C", "참고만")]


def _num(s):
    s = re.sub(r"[,\s원주%]", "", str(s or ""))
    m = re.match(r"^-?\d+(\.\d+)?$", s)
    return float(s) if m else None


def _doc_val(blocks, pat):
    """원문 표에서 라벨이 pat에 맞는 줄의 첫 숫자 값"""
    rx = re.compile(pat)
    for b in blocks or []:
        if b.get("t") != "table":
            continue
        pending = 0
        for r in b["rows"]:
            cells = [c for c in r if c]
            if not cells:
                continue
            if rx.search(re.sub(r"\s", "", " ".join(cells[:-1]) if len(cells) > 1 else cells[0])):
                vals = [v for v in map(_num, cells[1:]) if v is not None]
                if vals:
                    return vals[0]
                pending = 2                                  # 값이 바로 아래 줄(보통주식 등)에 있는 표
                continue
            if pending:
                vals = [v for v in map(_num, cells) if v is not None]
                if vals:
                    return vals[-1]
                pending -= 1
    return None


def _filing_size(tag, rcept_no, mcap_eok):
    """재료 크기 점수(0~30)와 한 줄 설명 — 공시 원문에서 숫자를 읽음 (원문 6시간 캐시, 공시 상세와 같은 캐시)"""
    import doc_detail
    key = f"doc:filing:{rcept_no}"
    d = cached(key, 6 * 3600, lambda: doc_detail.detail("filing", rcept_no))
    if not isinstance(d, dict) or d.get("error"):
        with _lock:
            _cache.pop(key, None)
        return 10, None
    bl = d.get("blocks")
    if tag == "공급계약":
        r = _doc_val(bl, r"매출액대비")
        if r is None:
            amt, rev = _doc_val(bl, r"계약금액"), _doc_val(bl, r"최근매출액")
            r = amt / rev * 100 if amt and rev else None
        if r is None:
            return 10, None
        s = 30 if r >= 50 else 25 if r >= 30 else 18 if r >= 15 else 12 if r >= 10 else 6 if r >= 5 else 0
        return s, f"매출 대비 {r:.0f}%"
    if tag == "무상증자":
        r = _doc_val(bl, r"1주당신주배정")
        if r is None:
            return 12, None
        return (28 if r >= 1 else 18 if r >= 0.5 else 8), f"1주당 {r:g}주 배정"
    if tag == "자사주":
        amt = _doc_val(bl, r"취득예정금액|계약금액|소각예정금액|소각할주식의총액")
        if amt and mcap_eok:
            r = amt / 1e8 / mcap_eok * 100
            return (28 if r >= 5 else 22 if r >= 3 else 15 if r >= 1.5 else 8 if r >= 0.5 else 2), f"시총 대비 {r:.1f}%"
        return 10, (f"{amt / 1e8:,.0f}억" if amt else None)
    return 10, None


def _quote(code):
    """네이버: 시가총액(억)·지금 등락률 — 10분 캐시 (장중 +3% 미만도 등락이 보이게)"""
    def f():
        import stock_info as si
        out = {}
        try:
            b = si._get(f"{si.NAVER}/{code}/basic", timeout=6).json() or {}
            out["chg"] = si.num(b.get("fluctuationsRatio"))
        except Exception:
            pass
        try:
            out["mcap_eok"] = si.kr_profile(code).get("mcap_eok")
        except Exception:
            pass
        return out
    q = cached("q:" + code, 600, f)
    q = dict(q) if isinstance(q, dict) and not q.get("error") else {}
    def tv():                                            # 20일 평균 거래대금(억) — 하루 한 번이면 충분
        import stock_info as si
        d = si.kr_ohlcv(code, 45).tail(20)
        return {"tv20": float((d["close"] * d["volume"]).mean() / 1e8)}
    t = cached("tv20:" + code, 6 * 3600, tv)
    if isinstance(t, dict) and t.get("tv20") is not None:
        q["tv20"] = t["tv20"]
    return q


def _rank(g, today):
    """g 에 score·grade·parts(왜 이 점수인지) 채움"""
    parts = []
    def add(k, v, note=None):
        parts.append({"k": k, "v": round(v), "note": note})
    add("종류", g["kind_pts"] * 30 / 35, "·".join(g["tags"][:2]))
    add("크기", g.get("size_pts", 10), g.get("size_note"))
    fresh = 10 if g["main"]["day"] == today else 0
    note = "오늘" if fresh else "어제"
    if g["main"].get("fix"):
        fresh -= 20; note += " · 정정공시(재탕일 수 있음)"
    add("신선도", fresh, note)
    # 덩치: 대형주는 재료에 덜 움직임(감점). 소형주 가산점은 없음 — 크기 점수(매출·시총 대비)가 이미
    #       '회사 덩치 대비 재료 크기'를 반영하므로 또 주면 이중 계산. 대신 너무 작거나 거래가 적으면 감점
    #       (사고팔 때 호가가 비어 손해, 작전·테마성 공시가 많음). → 시총 1천억~1조가 가장 유리
    mc, tv = g.get("mcap_eok"), g.get("tv20")
    if mc:
        add("덩치", -15 if mc >= 30000 else -8 if mc >= 10000 else 0 if mc >= 1000 else -5 if mc >= 500 else -10,
            f"시총 {mc / 10000:.1f}조" if mc >= 10000 else f"시총 {mc:,.0f}억" + (" (초소형)" if mc < 500 else " (소형)" if mc < 1000 else ""))
    if tv is not None and tv < 10:
        add("거래", -10 if tv < 3 else -5, f"하루 평균 {tv:.1f}억 — 사고팔기 어려움")
    c = g.get("chg")
    if c is not None:
        add("덜 오름", 10 if c < 2 else 5 if c < 5 else 0, f"{c:+.1f}%")
    if g.get("news_pts"):
        add("관심", min(15, g["news_pts"] * 0.6), f"기사 {len(g.get('news') or [])}건+")
    if "유상증자·CB" in g["neg"]:
        add("악재", -15, "유상증자·CB 같이 나옴")
    g["score"] = max(0, min(100, round(sum(p["v"] for p in parts))))
    g["parts"] = parts
    for cut, gr, label in GRADES:
        if g["score"] >= cut:
            g["grade"], g["grade_label"] = gr, label
            break


def news_radar():
    sp = os.path.join(REPO, "surge-study")
    if sp not in sys.path:
        sys.path.insert(0, sp)
    import candidates as C
    from concurrent.futures import ThreadPoolExecutor
    now = bot.now()
    import datetime as _dt
    def _prev_bday(x):                                    # 바로 앞 평일
        x -= _dt.timedelta(days=1)
        while x.weekday() >= 5:
            x -= _dt.timedelta(days=1)
        return x
    base = now if now.weekday() < 5 else _prev_bday(now)  # 주말엔 '금요일·목요일' 공시를 보여 줌 (주말엔 공시가 거의 없음)
    today = base.strftime("%Y%m%d")
    yday = _prev_bday(base).strftime("%Y%m%d")
    fl, dart_err = [], None
    for d in (today, yday):
        got = cached("dart-list:" + d, 180 if d == today else 3600, lambda d=d: _dart_list(d))
        if isinstance(got, dict):                         # 실패 → {"error": ...}
            dart_err = got.get("error")
            with _lock:
                _cache.pop("dart-list:" + d, None)
            continue
        fl += [{**x, "day": d} for x in got]
    # 오늘 장중 기록(+3%↑만 기록됨)으로 지금 등락
    rows = _intraday_rows(now.strftime("%Y-%m-%d"))
    chg, mc = {}, {}
    for r in sorted(rows, key=lambda r: r["time"]):
        try:
            chg[r["code"]] = float(r["chg"]); mc[r["code"]] = float(r.get("mcap_eok") or 0)
        except ValueError:
            pass
    market_open = now.weekday() < 5 and (9, 0) <= (now.hour, now.minute) <= (15, 30)
    by = {}
    for x in fl:
        t = re.sub(r"\s", "", x.get("report_nm") or "")
        pos = [(tag, pts) for tag, pat, pts in C.CAT_RULES if re.search(pat, t)]
        neg = [(tag, pts) for tag, pat, pts in C.NEG_RULES if re.search(pat, t)]
        if not pos and not neg:
            continue
        code = x["stock_code"]
        g = by.setdefault(code, {"code": code, "name": x["corp_name"], "items": [], "pts": 0, "neg": [], "tags": []})
        fix = bool(re.search(r"기재정정|첨부정정|정정", t[:8]))
        it = {"title": x.get("report_nm", "").strip(), "rcept_no": x["rcept_no"], "day": x["day"], "fix": fix}
        g["items"].append(it)
        for tag, pts in pos:
            if tag not in g["tags"]:
                g["tags"].append(tag)
            # 대표 공시 = 점수 높은 것 → 원공시(정정 아님) → 오늘 → 최신 순
            k = (pts, not fix, x["day"] == today, x["rcept_no"])
            if not g.get("main_k") or k > g["main_k"]:
                g["main_k"], g["main"], g["kind_pts"], g["main_tag"] = k, it, pts, tag
            g["pts"] = max(g["pts"], pts if x["day"] == today else pts * 0.7)
        g["neg"] += [tag for tag, _ in neg if tag not in g["neg"]]
    for g in by.values():
        g["chg"] = chg.get(g["code"])
        g["mcap_eok"] = mc.get(g["code"])
        g["latest"] = max(i["rcept_no"] for i in g["items"])
        g["items"].sort(key=lambda i: (i is not g.get("main"), i["rcept_no"]))   # 대표 공시를 맨 위로
        g.pop("main_k", None)
    good = [g for g in by.values() if g["pts"] > 0 and "거래소 경고" not in g["neg"]]
    good.sort(key=lambda g: (-g["pts"], -int(g["latest"])))
    good = good[:45]
    # 순위용 숫자: 지금 등락·시총(네이버) + 공시 원문의 크기(매출 대비 % 등)
    def fill(g):
        q = _quote(g["code"])
        if q.get("chg") is not None:
            g["chg"] = q["chg"]
        g["mcap_eok"] = q.get("mcap_eok") or g["mcap_eok"]
        g["tv20"] = q.get("tv20")
        try:
            g["size_pts"], g["size_note"] = _filing_size(g["main_tag"], g["main"]["rcept_no"], g["mcap_eok"])
        except Exception:
            g["size_pts"], g["size_note"] = 10, None
        return g
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(fill, good))
    for g in good:
        g["moved"] = g["chg"] is not None and g["chg"] >= 5
        _rank(g, today)
    good.sort(key=lambda g: (g["moved"], -g["score"], -int(g["latest"])))
    bad = sorted([g for g in by.values() if g["neg"]], key=lambda g: -int(g["latest"]))
    for g in bad:
        g.setdefault("moved", False)
    # 장중 '막 시작' 종목 — 왜 움직이는지(공시·뉴스)
    early = []
    try:
        e, _, _, _ = _intraday_scan(rows)
        early = [{"code": x["code"], "name": x["name"], "chg": x["chg"], "big": x["big"]} for x in e[:12]]
    except Exception:
        pass
    # 뉴스: 덜 움직인 재료 종목 상위 15 + 막 시작 종목
    want = [g for g in good if not g["moved"]][:15] + early
    def one(x):
        try:
            nw = _news(x["name"], 8)
        except Exception:
            nw = []
        titles = [n["title"] for n in nw]
        pts, why, warn, th = C.news_score(titles, ["오늘 공시: " + "·".join(x.get("tags") or [])], x.get("chg") or 0, [])
        return x["code"], {"news": [{"title": n["title"], "source": n.get("source"), "link": n.get("link"), "date": n.get("date")} for n in nw[:3]],
                           "news_pts": pts, "news_why": why, "news_warn": warn, "themes": th}
    with ThreadPoolExecutor(6) as ex:
        nmap = dict(ex.map(one, want))
    for x in good + early:
        x.update(nmap.get(x["code"], {}))
    for g in good:                                        # 뉴스 관심까지 넣어 최종 순위
        _rank(g, today)
    good.sort(key=lambda g: (g["moved"], -g["score"], -int(g["latest"])))
    for i, g in enumerate([g for g in good if not g["moved"]], 1):
        g["rank"] = i
    gcodes = {g["code"]: g for g in good}
    for x in early:
        g = gcodes.get(x["code"])
        x["filing_tags"] = g["tags"] if g else []
        x["explained"] = bool(g) or bool(x.get("news_why"))
    return {"time": now.strftime("%H:%M"), "market_open": market_open, "n_filings": len(fl), "dart_error": dart_err,
            "fresh": [g for g in good if not g["moved"]][:25], "moved": [g for g in good if g["moved"]][:15],
            "bad": bad[:15], "early": early, "today": today, "yday": yday, "weekend": now.weekday() >= 5}


# ── 발굴 탭: 급등 후보 · 💎 아빠 매매일지 DNA 20선(가치주) · 애크먼 TOP10 ─────────────────────────────
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


def picks_surge(date=None):
    """급등 후보 — date 없으면 최신. 날짜 목록·그 후보의 다음 날 성적·그날 실제 급등주까지"""
    try:
        idx = json.loads(gh_text("surge-study/data/candidates/index.json", ttl=900)).get("dates", [])
    except Exception:
        idx = []
    path = f"surge-study/data/candidates/{date}.json" if date else "surge-study/data/candidates/latest.json"
    j = json.loads(gh_text(path, ttl=900 if not date or (idx and date == idx[0]["date"]) else 86400))
    g = j.get("graded")
    nxt = {r["code"]: r.get("next_chg") for r in (g or {}).get("results", [])}
    items = [{"rank": i, **c, "next_chg": nxt.get(c["code"])} for i, c in enumerate(j["candidates"][:10], 1)]
    today_live = None
    if not date and not g and j["date"] < bot.now().strftime("%Y-%m-%d"):   # 채점 전(오늘 장중·마감 직후) → 장중 기록으로 미리 대조
        try:
            rows = _intraday_rows(bot.now().strftime("%Y-%m-%d"))
            if rows:
                last, mx = {}, {}
                for r in sorted(rows, key=lambda r: r["time"]):
                    try:
                        c_ = float(r["chg"])
                    except ValueError:
                        continue
                    last[r["code"]] = c_
                    mx[r["code"]] = max(mx.get(r["code"], -99), c_)
                floor = min(last.values()) if last else None
                for x in items + [{"code": c["code"]} for c in j["candidates"][10:20]]:
                    if x["code"] in last:
                        x["today"], x["today_max"] = last[x["code"]], mx[x["code"]]
                hit = sum(1 for x in items if (x.get("today_max") or 0) >= 10)
                today_live = {"time": max(r["time"] for r in rows), "floor": round(floor or 0), "hit10": hit, "n": len(items)}
        except Exception:
            today_live = None
    surgers = []
    try:                                          # 그날 실제로 급등한 종목(+15%↑) — 왜 올랐나
        dj = json.loads(gh_text(f"surge-study/data/daily/{j['date']}.json", ttl=900 if not date else 86400))
        cand = {c["code"] for c in j["candidates"]}
        for x in sorted(dj.get("surgers", []), key=lambda x: -x.get("chg", 0))[:30]:
            surgers.append({"code": x["code"], "name": x["name"], "market": x.get("market"), "chg": round(x.get("chg", 0), 1),
                            "catalysts": x.get("catalysts") or [], "themes": x.get("themes") or [],
                            "news": [n.get("title") for n in (x.get("news") or [])[:1]], "picked": x["code"] in cand,
                            "big": bool(x.get("big"))})
        ctx = dj.get("context") or {}
    except Exception:
        ctx = {}
    return {"kind": "surge", "date": j["date"], "method": j.get("method"), "n_scored": j.get("n_scored"),
            "items": items, "more": j["candidates"][10:20], "prev": j.get("prev"), "graded": g, "today_live": today_live, "hot_themes": j.get("hot_themes") or [],
            "dates": idx, "surgers": surgers, "context": ctx, "live": None if date else _try(intraday_now, None),
            "morning": None if date else _try(lambda: cached("us_overnight", 3600, us_overnight), None)}


def us_overnight():
    """🌅 밤사이 미국 동종 3사(us_peers.json) 수익률 → 오늘 크게 움직일 코스피 대형주
       백테스트(2022~2026 검증): 동종 3사 평균 +3%↑면 그날 평균 +1.3%, +5%↑면 +2.2%(+5%↑ 확률 2.7배) — 대부분 시가 갭에 반영"""
    import data_sources as ds
    from concurrent.futures import ThreadPoolExecutor
    P = json.loads(gh_text("surge-study/data/us_peers.json", ttl=86400))["stocks"]
    syms = sorted({x for v in P.values() for x in v["peers"]})

    def one(sym):
        try:
            df = ds._yahoo(sym, "5d")
            c = df["close"]
            return sym, (float(c.iloc[-1] / c.iloc[-2] * 100 - 100), f"{df.index[-1]:%Y-%m-%d}")
        except Exception:
            return sym, None
    with ThreadPoolExecutor(8) as ex:
        R = {k: v for k, v in ex.map(one, syms) if v}
    if not R:
        return {"error": "미국 시세를 못 받음"}
    us_date = max(v[1] for v in R.values())
    rows = []
    for code, v in P.items():
        rs = [(x, R[x][0]) for x in v["peers"] if x in R and R[x][1] == us_date]
        if len(rs) < 2:
            continue
        avg = sum(r for _, r in rs) / len(rs)
        cor = sum(v.get("corr") or [0]) / max(1, len(v.get("corr") or []))
        if cor < 0.12:                             # 연동이 약한 짝은 뺌 (백테스트: 상관 클수록 효과 큼)
            continue
        rows.append({"code": code, "name": v["name"], "avg": round(avg, 2), "peers": [[x, round(r, 1)] for x, r in rs],
                     "link": "강" if cor >= 0.25 else "중" if cor >= 0.17 else "약"})
    rows.sort(key=lambda x: -x["avg"])
    return {"us_date": us_date, "up": [x for x in rows if x["avg"] >= 2][:15], "down": [x for x in rows[::-1] if x["avg"] <= -3][:6],
            "n": len(rows)}


def intraday_loop():
    """서버가 직접 장중 10분마다 상승 종목 스냅샷 (GitHub 예약 실행은 지연이 잦아서) → state/intraday/kr-날짜.csv"""
    sp = os.path.join(REPO, "surge-study")
    if sp not in sys.path:
        sys.path.insert(0, sp)
    while True:
        try:
            n = bot.now()
            if n.weekday() < 5 and (9, 0) <= (n.hour, n.minute) <= (15, 40):
                import intraday
                day, df = intraday.kr()
                if day and not df.empty:
                    d = os.path.join(bot.STATE_DIR, "intraday")
                    os.makedirs(d, exist_ok=True)
                    p = os.path.join(d, f"kr-{day}.csv")
                    df.to_csv(p, mode="a", header=not os.path.exists(p), index=False)
                    with _lock:
                        _cache.pop("picks:surge", None)       # 다음 요청에 새 스냅샷 반영
        except Exception as e:
            print("장중 스냅샷 실패:", e, flush=True)
        time.sleep(600)


EARLY = {"small": (3, 8, 5), "big": (2, 4, 30)}   # (상승률 하한, 상한, 10분 거래대금 증가 최소 억원)


def _intraday_rows(day):
    rows = []
    local = os.path.join(bot.STATE_DIR, "intraday", f"kr-{day}.csv")
    if os.path.exists(local):
        rows += list(csv.DictReader(open(local, encoding="utf-8")))
    if day == bot.now().strftime("%Y-%m-%d"):
        try:
            rows += list(csv.DictReader(io.StringIO(gh_text(f"surge-study/data/intraday/kr/{day}.csv", ttl=300))))
        except Exception:
            pass
    return rows


def _intraday_scan(rows):
    """스냅샷 → 종목별 시계열 → (막 움직이기 시작한 종목 목록, 이미 오른 종목 목록, 마지막 시각)
       막 시작 = 아직 덜 올랐는데(소형 +3~8% · 대형 +2~4%) 직전 스냅샷 이후 거래대금이 확 늘어남
               (오늘 거래대금의 25%↑가 최근 한 구간에 몰림 & 소형 5억·대형 30억↑)"""
    ser = {}
    for r in rows:
        try:
            x = {"t": r["time"], "chg": float(r["chg"]), "tv": float(r.get("tv_eok") or 0), "mc": float(r.get("mcap_eok") or 0),
                 "lu": r.get("limit_up") == "True"}
        except (ValueError, KeyError):
            continue
        if re.search(r"\d?우[A-C]?$", r.get("name", "")):
            continue
        s = ser.setdefault(r["code"], {"code": r["code"], "name": r["name"], "market": r.get("market"), "pts": {}})
        s["pts"][x["t"]] = x                                  # 같은 시각 중복(서버+GitHub)은 하나로
    if not ser:
        return [], [], None, []
    last_t = max(t for s in ser.values() for t in s["pts"])
    early, ran = [], []
    for s in ser.values():
        ps = [s["pts"][t] for t in sorted(s["pts"])]
        cur = ps[-1]
        big = cur["mc"] >= 50000
        lo, hi, need = EARLY["big" if big else "small"]
        first_early = None
        for i in range(1, len(ps)):                          # 그날 '막 시작' 조건을 처음 만족한 시각
            d = ps[i]["tv"] - ps[i - 1]["tv"]
            if lo <= ps[i]["chg"] < hi and d >= need and ps[i]["tv"] > 0 and d / ps[i]["tv"] >= 0.25:
                first_early = {"t": ps[i]["t"], "chg": ps[i]["chg"], "dtv": round(d, 1), "share": round(d / ps[i]["tv"], 2)}
                break
        item = {"code": s["code"], "name": s["name"], "market": s["market"], "big": big, "chg": cur["chg"], "tv_eok": cur["tv"],
                "mcap_eok": cur["mc"], "first": ps[0]["t"], "max": max(p["chg"] for p in ps), "limit_up": cur["lu"], "t": cur["t"]}
        if first_early:
            item["early"] = first_early
        if cur["t"] == last_t and first_early and cur["chg"] < hi + 2:
            early.append(item)
        elif cur["t"] == last_t and ((big and cur["chg"] >= 4) or cur["chg"] >= 10) and (big or cur["tv"] >= 10):
            ran.append(item)
        s["item"] = item
    early.sort(key=lambda x: -(x["early"]["share"] * x["early"]["dtv"]))
    ran.sort(key=lambda x: (not x["big"], -x["chg"]))
    return early, ran, last_t, [s["item"] for s in ser.values() if "early" in s.get("item", {})]


def _early_grade(days=10):
    """지난 장 '막 시작' 포착의 성적 — 포착 시점 상승률 → 그날 마지막 스냅샷 상승률 (마감까지 더 올랐나)"""
    d = os.path.join(bot.STATE_DIR, "intraday")
    today = bot.now().strftime("%Y-%m-%d")
    fs = sorted(f[3:13] for f in os.listdir(d) if f.startswith("kr-") and f[3:13] < today) if os.path.isdir(d) else []
    gains, n_days = [], 0
    for day in fs[-days:]:
        r = _intraday_scan(_intraday_rows(day))
        if not r[0] and not r[3]:
            continue
        n_days += 1
        gains += [x["chg"] - x["early"]["chg"] for x in r[3]]   # 마지막에 스냅샷에서 빠진(상승폭 줄어든) 종목은 그 시점 값
    if not gains:
        return None
    gains.sort()
    return {"days": n_days, "n": len(gains), "avg": round(sum(gains) / len(gains), 2), "med": round(gains[len(gains) // 2], 2),
            "up3": round(sum(1 for g in gains if g >= 3) / len(gains), 2), "down": round(sum(1 for g in gains if g < 0) / len(gains), 2)}


def intraday_now():
    """📡 장중 — 위: 막 움직이기 시작한 종목(관찰용) · 아래(접힘): 이미 오른 종목(쫓지 말 것) + 지난 포착 성적"""
    today = bot.now().strftime("%Y-%m-%d")
    rows = _intraday_rows(today)
    if not rows:
        return None
    early, ran, last_t, _ = _intraday_scan(rows)
    return {"date": today, "time": last_t, "early": early[:15], "items": ran[:25], "n": len(ran),
            "grade": cached("early-grade", 3600, _early_grade), "rule": EARLY}


def picks_value():
    import tempfile
    vb = os.path.join(REPO, "value-bot")
    if vb not in sys.path:
        sys.path.insert(0, vb)
    import recommend
    from value_dna import load_profile
    tmp = tempfile.mkdtemp(prefix="vb-")
    for fn in ("universe.csv", "profile.json", "holdings.txt", "recent_buys.txt", "DATA_ASOF", "pinned.txt"):
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
        if hasattr(recommend, "apply_pinned"):
            picked = recommend.apply_pinned(picked, 20, os.path.join(tmp, "pinned.txt"))
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


def hero_extras(market):
    """대가 채점에 크기와 상관없이 늘 넣는 종목 — 내 계좌 · 아는 회사(heroes_pool.txt) · 가치주 후보 · (해외) 대표 종목"""
    import data_sources as ds
    import heroes
    out = []

    def add(code, name, src, held=False):
        code = str(code or "").strip()
        if market == "kr":
            code = re.sub(r"\D", "", code)[-6:]
            if len(code) != 6:
                return
        if code:
            out.append({"code": code, "name": name, "src": src, "held": held})
    acct = _cache.get("account")
    acct = acct[1] if acct else None
    if not (isinstance(acct, dict) and acct.get("items")):
        acct = _try(account, {})
    if market == "kr":
        try:
            for l in gh_text("toss-bot/heroes_pool.txt", ttl=3600).splitlines():
                l = l.strip()
                if l and not l.startswith("#"):
                    c, _, n = l.partition(",")
                    add(c, n.strip() or None, "아는 회사")
        except Exception:
            pass
        by_name = {}
        try:
            for r in csv.DictReader(io.StringIO(gh_text("value-bot/universe.csv", ttl=3600).lstrip("\ufeff"))):
                add(r.get("ticker"), r.get("name"), "가치주 후보")
                by_name[r.get("name")] = r.get("ticker")
        except Exception:
            pass
        for i in (acct or {}).get("items") or []:
            if i.get("currency") != "USD":
                add(i.get("symbol"), i.get("name"), "내 계좌", True)
        try:                                          # value-bot 보유 목록(이름) — 계좌 API가 안 될 때 대비
            for l in gh_text("value-bot/holdings.txt", ttl=3600).splitlines():
                l = l.strip()
                if l and not l.startswith("#") and by_name.get(l):
                    add(by_name[l], l, "내 계좌", True)
        except Exception:
            pass
        try:
            cmap = {c["code"]: c for c in ds.load_corps()}
            for x in out:
                c = cmap.get(x["code"])
                if c:
                    x["corp_code"] = c.get("corp_code")
                    x["name"] = x["name"] or c.get("name")
        except Exception:
            pass
    else:
        for c, n in heroes.GLOBAL_POOL.get(market, []):
            add(c, n, "대표 종목")
        if market == "us":
            for i in (acct or {}).get("items") or []:
                if i.get("currency") == "USD":
                    add(i.get("symbol"), i.get("name"), "내 계좌", True)
    return out


# 🏛️ 대가 10인 — 한국(코스피 시총 2천억↑) + 해외(나라별 시총 2조원↑) 수천 종목을 서버 뒤 일꾼이 계속 채점해
#    state/heroes.db 에 저장 → 화면은 DB를 바로 읽음 (기다림 없음). chartpage/hero_db.py 참고
def picks_hero_db(market):
    import hero_db
    return hero_db.board(market)


PICKS = {"hero_us": (lambda: picks_hero_db("us"), 60), "hero_eu": (lambda: picks_hero_db("eu"), 60),
         "hero_cn": (lambda: picks_hero_db("cn"), 60), "hero_jp": (lambda: picks_hero_db("jp"), 60),
         "hero": (lambda: picks_hero_db("kr"), 60), "surge": (picks_surge, 900), "value": (picks_value, 3600), "ackman": (picks_ackman, 3600),
         "fund": (lambda: __import__("fund_sim").summary(), 120),
         "etf": (lambda: __import__("etf").summary(), 600),
         "fxh": (lambda: __import__("fx_hedge").summary(), 6 * 3600)}     # 💱 환헤지 vs 환노출 백테스트


def picks(kind):
    fn, ttl = PICKS.get(kind, PICKS["hero"])
    return swr("picks:" + kind, ttl, fn)


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
    try:                                          # 🏛️ 대가 10인 체크 — 한국은 DART 10년 재무로 (처음엔 받는 데 시간이 걸려 3초까지만 기다림)
        import heroes
        dd = None
        if not it.get("us") and it.get("corp_code"):
            from concurrent.futures import ThreadPoolExecutor, TimeoutError as TE
            import dart_fin
            ex = ThreadPoolExecutor(1)
            fut = ex.submit(dart_fin.build, it["corp_code"])
            try:
                dd = fut.result(timeout=3)
            except TE:
                dd = None                          # 백그라운드에서 계속 받음 → 다음에 열면 10년 기준
            ex.shutdown(wait=False)
        out = {**out, "heroes": heroes.score({**out, "dart": dd})}
    except Exception as e:
        out = {**out, "heroes": {"error": f"{type(e).__name__}: {str(e)[:120]}"}}
    # 어느 목록에 들어 있는지 표시 (보유·후보·20선·애크먼)
    tags = []
    try:
        s = bot.peek()
        if it["code"] in s["kr"]["positions"]:
            tags.append("🤖 봇 보유")
    except Exception:
        pass
    for kind, label in (("hero", "🏛️ 대가"), ("surge", "🚀 급등 후보"), ("value", "💎 자바 20선"), ("ackman", "🇺🇸 애크먼")):
        p = _cache.get("picks:" + kind)
        if p and isinstance(p[1], dict):
            for x in p[1].get("items", []):
                if (x.get("code") or x.get("t")) == it["code"]:
                    tags.append(f"{label} {x.get('rank') or ''}{'위' if x.get('rank') else ''}".strip())
                    if kind == "value" and x.get("held"):
                        tags.append("📌 내 계좌 보유")
    return {**out, "tags": tags}


def stock_extra(q, us_hint=None):
    """종목 상세의 느린 부분(사업요약 번역·매출비중) — 화면이 먼저 뜬 뒤 따로 받아 채움. 6시간 캐시"""
    import data_sources as ds
    import stock_info as si
    hits = ds.search(q.strip(), 1)
    if not hits:
        return {}
    it = hits[0]
    if us_hint and not it.get("us"):
        it = {"name": q.upper(), "code": q.upper(), "us": True}
    base = _cache.get("stock:" + it["code"])
    prof = (base[1].get("profile") if base and isinstance(base[1], dict) else None) or {}
    out = cached("extra:" + it["code"], 6 * 3600, lambda: si.extras(it, prof))
    if not (out.get("desc") or out.get("segments")):      # 둘 다 비면 다음에 다시
        with _lock:
            _cache.pop("extra:" + it["code"], None)
    return out


def fin_long(q):
    """종목 → DART 2015~최근 재무 전체 + 그해 말 종가 PER·PBR (장기 재무 화면)"""
    import data_sources as ds
    import dart_fin
    hits = ds.search(q.strip(), 1)
    if not hits:
        return {"error": f"'{q}' 종목을 찾지 못했습니다"}
    it = hits[0]
    if it.get("us"):
        return {"error": "해외 종목은 DART 공시가 없어 장기 재무를 지원하지 않음 (연간·분기 표는 야후 기준)"}
    if not it.get("corp_code"):
        return {"error": "DART 고유번호를 찾지 못함"}

    def closes():
        hit = _cache.get("stock:" + it["code"])
        o = hit[1].get("ohlc") if hit and isinstance(hit[1], dict) else None
        if not o:
            import stock_info as si
            df = si.kr_ohlcv(it["code"], 20000)
            o = {"d": [f"{x:%Y%m%d}" for x in df.index], "c": list(df["close"])}
        out = {}
        for d8, c in zip(o["d"], o["c"]):
            if c:
                out[d8[:4]] = c                   # 그해 마지막 거래일 종가
        return out
    cl = _try(closes, {})
    return {"name": it.get("name"), "code": it["code"], **dart_fin.build(it["corp_code"], cl)}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _role(self):
        """🌐 공개 주소(Funnel → mcp_server.py 의 /app)로 들어온 요청은 서버 안(localhost)에서 와도 무조건 보기 전용"""
        if self.headers.get("X-Toss-Public") == "1":
            return "viewer", "🌐 공개 주소"
        return role_info(self.client_address[0])

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

    def _send(self, code, body, ctype, cache="no-store", etag=None, gzkey=None):
        b = body if isinstance(body, bytes) else body.encode()
        gz = len(b) > 2048 and "gzip" in (self.headers.get("Accept-Encoding") or "") and not ctype.startswith("image/")
        if gz:                                    # 전체 기간 차트 데이터(수백 KB) → 보통 1/4 크기로
            hit = _gzc.get(gzkey) if gzkey else None
            if hit:
                b = hit
            else:
                import gzip
                b = gzip.compress(b, 6 if gzkey else 5)
                if gzkey:
                    _gzc[gzkey] = b                    # 정적 파일은 압축본을 기억 (매번 압축 안 함)
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        if gz:
            self.send_header("Content-Encoding", "gzip")
        if etag:
            self.send_header("ETag", etag)
        self.send_header("Cache-Control", cache)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _sse(self, code):
        import manual_trade as mt
        from ob_stream import HUB
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        HUB.touch(code)
        def emit(o):
            self.wfile.write(("data: " + json.dumps(o, ensure_ascii=False, default=str) + "\n\n").encode())
            self.wfile.flush()
        try:
            snap = mt.orderbook(code)                  # 처음 한 번은 REST 로 전체(상·하한가·현재가·최근 체결·오늘 시고저 포함)
            day0 = {}
            try:
                cs = bot.daily(mt.api(), code, 2)          # (날짜, 시, 고, 저, 종, 거래량) 과거 → 최신
                if cs:
                    t_ = cs[-1]
                    istoday = t_[0] == bot.now().strftime("%Y-%m-%d") or not code.isdigit()
                    day0 = {"open": t_[1], "high": t_[2], "low": t_[3], "vol": t_[5], "prev": (cs[-2][4] if len(cs) > 1 else None) if istoday else t_[4],
                            "today": istoday}
            except Exception:
                pass
            snap["day"] = day0
            try:
                snap["ticks"] = [{"p": mt._f(t.get("price")), "v": mt._f(t.get("volume")), "t": t.get("timestamp")}
                                 for t in (mt.api().trades(code, 30) or [])]
                with HUB.cv:
                    HUB.data.setdefault(code, {"v": 0}).setdefault("ticks", snap["ticks"])
            except Exception:
                pass
            up, lo = snap.get("upper"), snap.get("lower")
            cur = {**snap, "mode": "rest"}
            with HUB.cv:                                # 이 화면 기준으로 체결강도를 새로 셈
                h_ = HUB.data.setdefault(code, {"v": 0})
                h_.update(buy_v=0, sell_v=0, hi=None, lo=None, vol_add=0)
            emit(cur)
            ver, started, last_beat, last_emit = 0, time.time(), time.time(), 0
            while time.time() - started < 600:         # 10분마다 끊으면 브라우저가 알아서 다시 붙음
                HUB.touch(code)
                ver2, x = HUB.wait(code, ver, 5)
                if ver2 > ver:
                    ver = ver2
                    gap = 0.12 - (time.time() - last_emit)  # 화면 갱신은 초당 8번까지(체결이 몰려도)
                    if gap > 0:
                        time.sleep(gap)
                        ver, x = HUB.wait(code, 0, 0)       # 기다리는 동안 들어온 최신 값으로
                    if x.get("ob"):
                        cur.update(x["ob"])
                    if x.get("last") is not None:
                        cur["last"], cur["tts"] = x["last"], x.get("ts")
                    if x.get("ticks"):
                        cur["ticks"] = x["ticks"][:30]
                    if x.get("buy_v") is not None:             # 체결강도(추정) = 매수 주도 체결량 ÷ 매도 주도 × 100 (이 화면을 연 뒤부터)
                        bv, sv = x.get("buy_v") or 0, x.get("sell_v") or 0
                        cur["strength"] = round(bv / sv * 100, 1) if sv else None
                        cur["bs"] = [bv, sv]
                    if x.get("hi") is not None and cur["day"].get("today"):
                        cur["day"]["high"] = max(cur["day"].get("high") or 0, x["hi"])
                        cur["day"]["low"] = min(cur["day"].get("low") or x["lo"], x["lo"])
                    if x.get("vol_add") and cur["day"].get("vol") is not None and cur["day"].get("today"):
                        cur["day"]["vol_now"] = cur["day"]["vol"] + x["vol_add"]
                    cur.update(upper=up, lower=lo, mode=HUB.mode, err=HUB.err)
                    emit(cur); last_emit = last_beat = time.time()
                elif time.time() - last_beat > 15:        # 조용한 동안에도 연결 유지
                    self.wfile.write(b": ping\n\n"); self.wfile.flush(); last_beat = time.time()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        except Exception as e:
            try:
                emit({"error": f"{type(e).__name__}: {str(e)[:160]}"})
            except Exception:
                pass
        self.close_connection = True

    def do_GET(self):
        if not self._auth():
            return
        path = self.path.split("?")[0]
        if path == "/api/radar":
            try:
                out = bg_cached("radar", 120, news_radar)
            except Exception as e:
                out = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
            return self._send(200, json.dumps(out, ensure_ascii=False, default=str), "application/json; charset=utf-8")
        if path == "/api/scan":
            m = (parse_qs(urlparse(self.path).query).get("m") or ["kr"])[0]
            try:
                return self._send(200, json.dumps(scan_data(m), ensure_ascii=False, default=str), "application/json; charset=utf-8")
            except Exception as e:
                return self._send(200, json.dumps({"error": str(e)[:200]}, ensure_ascii=False), "application/json; charset=utf-8")
        if path == "/api/mini":
            qs = parse_qs(urlparse(self.path).query)
            try:
                out = mini_chart((qs.get("q") or [""])[0], (qs.get("us") or [""])[0] == "1")
            except Exception as e:
                out = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
            return self._send(200, json.dumps(out, ensure_ascii=False, default=str), "application/json; charset=utf-8")
        if path == "/api/stock-extra":
            qs = parse_qs(urlparse(self.path).query)
            try:
                out = stock_extra((qs.get("q") or [""])[0], (qs.get("us") or [""])[0] == "1")
            except Exception as e:
                out = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
            return self._send(200, json.dumps(out, ensure_ascii=False, default=str), "application/json; charset=utf-8")
        if path in ("/api/picks", "/api/stock"):
            qs = parse_qs(urlparse(self.path).query)
            try:
                if path == "/api/picks":
                    k, dd = (qs.get("k") or ["surge"])[0], (qs.get("d") or [""])[0]
                    if k == "surge" and re.fullmatch(r"\d{4}-\d{2}-\d{2}", dd):
                        out = cached("picks:surge:" + dd, 900, lambda: picks_surge(dd))
                    elif k == "fund" and self._role()[0] == "viewer":   # 보기 전용: 내 펀드 금액·주수 숨김
                        out = cached("picks:fund:viewer", 120, lambda: __import__("fund_sim").summary(viewer=True))
                    else:
                        out = picks(k)
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
        if path == "/api/popular":                # 🔥 토스 인기 TOP 10 (종목 탭 첫 화면)
            tag = "us" if (parse_qs(urlparse(self.path).query).get("m") or ["kr"])[0] == "us" else "kr"
            out = cached("popular:" + tag, 60, lambda: toss_popular(tag))
            return self._send(200, json.dumps(out, ensure_ascii=False, default=str), "application/json; charset=utf-8")
        if path == "/api/screen":                 # 🔎 재무 필터 (발굴 탭)
            m = (parse_qs(urlparse(self.path).query).get("m") or ["kr"])[0]
            try:
                out = cached("screen:" + m, 300, lambda: __import__("hero_db").screen(m))
            except Exception as e:
                out = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
            return self._send(200, json.dumps(out, ensure_ascii=False, default=str), "application/json; charset=utf-8")
        if path == "/api/fin":                    # 장기·전체 재무제표 (DART)
            q = (parse_qs(urlparse(self.path).query).get("q") or [""])[0]
            try:
                out = cached("fin:" + q, 12 * 3600, lambda: fin_long(q))
                if out.get("error"):
                    with _lock:
                        _cache.pop("fin:" + q, None)
            except Exception as e:
                out = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
            return self._send(200, json.dumps(out, ensure_ascii=False, default=str), "application/json; charset=utf-8")
        if path == "/api/dividend/upcoming":      # 💰 시장 전체 — 곧 기준일이 오는 배당 (최근 공시)
            try:
                import dividend
                out = dividend.upcoming()
            except Exception as e:
                out = {"items": [], "error": f"{type(e).__name__}: {str(e)[:200]}"}
            return self._send(200, json.dumps(out, ensure_ascii=False, default=str), "application/json; charset=utf-8")
        if path == "/api/dividend":               # 💰 배당 플래너 — 5년 배당 공시 평균 + 확정 공시 (DART)
            q = re.sub(r"\D", "", (parse_qs(urlparse(self.path).query).get("q") or [""])[0])[-6:]
            try:
                if len(q) != 6:
                    raise ValueError("6자리 종목코드가 필요해요")
                import dividend
                out = swr("div:" + q, 6 * 3600, lambda: dividend.build(q))
                if out.get("error"):
                    with _lock:
                        _cache.pop("div:" + q, None)
            except Exception as e:
                out = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
            return self._send(200, json.dumps(out, ensure_ascii=False, default=str), "application/json; charset=utf-8")
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
        if path == "/api/ob-stream":              # ⚡ 실시간 호가 (Server-Sent Events) — 토스 웹소켓 → 브라우저
            code = (parse_qs(urlparse(self.path).query).get("q") or [""])[0].strip().upper()
            if not re.fullmatch(r"[0-9A-Z.\-]{1,12}", code):
                return self._send(400, "bad code", "text/plain")
            import manual_trade as mt
            if not mt.enabled()[0]:
                return self._send(503, "disabled", "text/plain")
            return self._sse(code)
        if path in ("/api/fills", "/api/reserve"):  # 🧾 체결내역 · ⏰ 예약(조건)주문 — 주인만
            qs = parse_qs(urlparse(self.path).query)
            code = (qs.get("q") or [""])[0].strip().upper() or None
            J = lambda c, o: self._send(c, json.dumps(o, ensure_ascii=False, default=str), "application/json; charset=utf-8")
            if code and not re.fullmatch(r"[0-9A-Z.\-]{1,12}", code):
                return J(400, {"error": "종목 코드가 올바르지 않습니다"})
            if self._role()[0] == "viewer":
                return J(403, {"error": "보기 전용"})
            import manual_trade as mt
            if not mt.enabled()[0]:
                return J(200, {"error": mt.enabled()[1], "disabled": True})
            try:
                if path == "/api/fills":
                    days = max(1, min(90, int((qs.get("days") or ["7"])[0] or 7)))
                    return J(200, mt.history(code, days))
                return J(200, {"items": mt.reservations(code)})
            except Exception as e:
                return J(200, {"error": f"{type(e).__name__}: {str(e)[:200]}"})
        if path in ("/api/orderbook", "/api/trade"):   # 📒 호가창(누구나) · 주문 화면 정보(주인만)
            code = (parse_qs(urlparse(self.path).query).get("q") or [""])[0].strip().upper()
            J = lambda c, o: self._send(c, json.dumps(o, ensure_ascii=False, default=str), "application/json; charset=utf-8")
            if not re.fullmatch(r"[0-9A-Z.\-]{1,12}", code):
                return J(400, {"error": "종목 코드가 올바르지 않습니다"})
            import manual_trade as mt
            ok, why = mt.enabled()
            if not ok:
                return J(200, {"error": why, "disabled": True})
            if path == "/api/trade" and self._role()[0] == "viewer":
                return J(403, {"error": "보기 전용"})
            try:
                return J(200, mt.orderbook(code) if path == "/api/orderbook" else {**mt.info(code), "enabled": True})
            except Exception as e:
                return J(200, {"error": f"{type(e).__name__}: {str(e)[:200]}"})
        if path == "/api/data":
            try:
                d = data()
                role, why = self._role()
                d = {**(for_viewer(d) if role == "viewer" else {**d, "viewer": False}), "role_why": why}
                return self._send(200, json.dumps(d, ensure_ascii=False, default=str), "application/json; charset=utf-8")
            except Exception as e:
                return self._send(500, json.dumps({"error": str(e)}), "application/json")
        name = {"/": "index.html"}.get(path, path.lstrip("/"))
        fp = os.path.normpath(os.path.join(STATIC, name))
        if not fp.startswith(STATIC) or not os.path.isfile(fp):
            return self._send(404, "not found", "text/plain")
        ctype = {".html": "text/html; charset=utf-8", ".json": "application/manifest+json", ".png": "image/png",
                 ".js": "text/javascript"}.get(os.path.splitext(fp)[1], "application/octet-stream")
        # ⚡ 정적 파일: 바뀌지 않았으면 304(본문 없이) — 앱을 열 때마다 220KB를 다시 받지 않음
        st_ = os.stat(fp)
        etag = f'"{int(st_.st_mtime)}-{st_.st_size}"'
        cache = "no-cache" if fp.endswith(".html") else "public, max-age=604800"   # html 은 매번 확인, js·아이콘은 7일
        if self.headers.get("If-None-Match") == etag:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", cache)
            self.end_headers()
            return
        self._send(200, open(fp, "rb").read(), ctype, cache=cache, etag=etag, gzkey=fp + etag)

    def do_POST(self):
        if not self._auth():
            return
        if self._role()[0] == "viewer":   # 보기 전용은 아무것도 바꿀 수 없음
            return self._send(403, json.dumps({"error": "보기 전용"}, ensure_ascii=False), "application/json; charset=utf-8")
        if self.path in ("/api/order", "/api/order/cancel", "/api/order/modify", "/api/reserve/cancel"):   # 💸 실제 주문 — 주인만(위에서 보기 전용 차단)
            J = lambda c, o: self._send(c, json.dumps(o, ensure_ascii=False, default=str), "application/json; charset=utf-8")
            org, host = self.headers.get("Origin"), self.headers.get("Host") or ""
            if (self.headers.get("X-Toss-Dash") != "1" or "application/json" not in (self.headers.get("Content-Type") or "")
                    or (org and urlparse(org).netloc != host)):
                return J(403, {"error": "대시보드 화면에서만 주문할 수 있어요"})
            n = int(self.headers.get("Content-Length") or 0)
            if n > 4096:
                return J(413, {"error": "too large"})
            body = json.loads(self.rfile.read(n) or b"{}")
            import manual_trade as mt
            try:
                if self.path == "/api/order":
                    mc = None
                    with _lock:
                        hit = _cache.get("stock:" + str(body.get("code") or ""))
                    try:
                        mc = ((hit[1] if isinstance(hit, tuple) else hit or {}).get("profile") or {}).get("mcap_eok")
                    except Exception:
                        mc = None
                    out = mt.place(body, mcap_eok=mc)       # 텔레그램 알림 없음(아빠가 있는 방으로 갈 수 있어서) — 기록은 state/manual_orders.jsonl
                elif self.path == "/api/order/modify":
                    out = mt.modify(str(body.get("order_id") or ""), body.get("price"), body.get("qty"))
                elif self.path == "/api/reserve/cancel":
                    out = mt.cancel_reservation(str(body.get("id") or ""))
                else:
                    out = mt.cancel(str(body.get("order_id") or ""))
                return J(200, out)
            except mt.Reject as e:
                return J(200, {"ok": False, "error": str(e)})
            except Exception as e:
                return J(200, {"ok": False, "error": f"주문 실패 — {type(e).__name__}: {str(e)[:220]}"})
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
    import hero_db
    hero_db.init(os.path.join(bot.STATE_DIR, "heroes.db"))
    hero_db.start(hero_extras)                   # 🏛️ 대가 채점 일꾼 (뒤에서 계속)
    threading.Thread(target=warm_up, daemon=True).start()
    threading.Thread(target=intraday_loop, daemon=True).start()
    import etf
    threading.Thread(target=etf.worker, daemon=True).start()   # 📦 ETF: KRX 일별 데이터 채우기 (매시간)
    ThreadingHTTPServer((host, port), H).serve_forever()
