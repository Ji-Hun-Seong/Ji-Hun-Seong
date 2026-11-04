"""토스봇 대시보드 — 서버에서 상시 실행(systemd), 폰에서는 Tailscale(비공개 네트워크)로 접속

  .venv/bin/python dashboard.py          # 포트 8080 (DASH_PORT로 변경)
  차트 탭: 종목 검색 → 볼린저(책 기법)·자사주 공시·외국인 수급 판정 (chartpage/ 모듈, 별도 서버 없음)
  선택: .env 에 DASH_PASSWORD=... 를 넣으면 접속 시 비밀번호(아이디는 아무거나)를 물어봄

투자 원칙: 장기 9 : 단기 1 (단기는 최대 2) — 홈 '장기·단기 비율' 카드, 발굴 '🏛️ 영웅' 목록, 종목 상세 '영웅 체크'
            (그레이엄·버핏·피셔·린치·애크먼 기준, chartpage/heroes.py)
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
    # 장기 보유 종목의 영웅 등급 (발굴 '영웅' 목록이 계산돼 있으면)
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
    for k in ("surge", "value", "ackman", "hero"):  # 발굴 목록도 미리 (종목 상세의 '어느 목록' 표시에 씀) · 영웅은 1분쯤 걸려 마지막
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
            "items": items, "more": j["candidates"][10:20], "prev": j.get("prev"), "graded": g,
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


def intraday_now():
    """📡 지금 움직이는 종목 — 장중 스냅샷(서버 10분마다 + GitHub surge-study/data/intraday/kr/오늘.csv)
       대형주(시총 5조↑) +4%↑ · 그 외 +10%↑(거래대금 10억↑, 우선주 제외), 처음 포착 시각과 지금 상승률"""
    today = bot.now().strftime("%Y-%m-%d")
    rows = []
    local = os.path.join(bot.STATE_DIR, "intraday", f"kr-{today}.csv")
    if os.path.exists(local):
        rows += list(csv.DictReader(open(local, encoding="utf-8")))
    try:
        rows += list(csv.DictReader(io.StringIO(gh_text(f"surge-study/data/intraday/kr/{today}.csv", ttl=300))))
    except Exception:
        pass
    if not rows:
        return None
    last_t = max(r["time"] for r in rows)
    by = {}
    for r in rows:
        try:
            chg, mc, tv = float(r["chg"]), float(r.get("mcap_eok") or 0), float(r.get("tv_eok") or 0)
        except ValueError:
            continue
        x = by.setdefault(r["code"], {"code": r["code"], "name": r["name"], "market": r["market"], "first": r["time"], "max": chg, "mcap_eok": mc})
        x["max"] = max(x["max"], chg)
        if r["time"] >= x.get("t", ""):
            x.update(t=r["time"], chg=chg, tv_eok=tv, mcap_eok=mc, limit_up=r.get("limit_up") == "True")
    out = []
    for x in by.values():
        big = x["mcap_eok"] >= 50000
        if x.get("t") != last_t:                  # 최근 스냅샷에서 빠졌으면(상승폭 줄어듦) 제외
            continue
        if re.search(r"\d?우[A-C]?$", x["name"]) or (not big and x["tv_eok"] < 10):
            continue
        if (big and x["chg"] >= 4) or x["chg"] >= 10:
            out.append({**x, "big": big})
    out.sort(key=lambda x: (not x["big"], -x["chg"]))
    return {"date": today, "time": last_t, "items": out[:25], "n": len(out)}


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


def hero_pool():
    """채점 후보 = toss-bot/heroes_pool.txt(내가 아는 회사) + value-bot 가치주 후보 + 내 계좌 보유 종목"""
    import data_sources as ds
    pool = {}

    def add(code, name, src, held=False):
        code = re.sub(r"\D", "", str(code or ""))[-6:]
        if len(code) != 6:
            return
        p = pool.setdefault(code, {"code": code, "name": name, "src": [], "held": False})
        if src not in p["src"]:
            p["src"].append(src)
        p["held"] = p["held"] or held
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
    acct = _cache.get("account")
    acct = acct[1] if acct else None
    if not (isinstance(acct, dict) and acct.get("items")):
        acct = _try(account, {})
    for i in (acct or {}).get("items") or []:
        if i.get("currency") != "USD":
            add(i.get("symbol"), i.get("name"), "내 계좌", True)
    try:                                          # value-bot 보유 목록(이름) — 계좌 API가 안 될 때 대비
        for l in gh_text("value-bot/holdings.txt", ttl=3600).splitlines():
            l = l.strip()
            if l and not l.startswith("#"):
                if by_name.get(l):
                    add(by_name[l], l, "내 계좌", True)
                    continue
                h = ds.search(l, 1)
                if h and h[0].get("name") == l and not h[0].get("us"):
                    add(h[0]["code"], l, "내 계좌", True)
    except Exception:
        pass
    for p in pool.values():
        try:
            h = ds.search(p["code"], 1)
            if h:
                p["corp_code"] = h[0].get("corp_code")
                p["name"] = p["name"] or h[0].get("name")
        except Exception:
            pass
    return list(pool.values())


def picks_hero():
    import heroes
    t0 = time.time()
    b = heroes.board(hero_pool())
    return {"kind": "hero", "asof": bot.now().strftime("%Y-%m-%d %H:%M"), "took": round(time.time() - t0, 1),
            "principles": heroes.PRINCIPLES, "heroes": [{"key": k, "name": n, "icon": i, "theme": th, "motto": m}
                                                        for k, n, i, th, m in heroes.HEROES], **b}


def picks_hero_global(market):
    """발굴 › 영웅 › 🇺🇸 미국 · 🇪🇺 유럽 · 🇨🇳 중국 · 🇯🇵 일본 — 시장별 대표 종목을 같은 6인 기준으로"""
    import heroes
    t0 = time.time()
    pool = [{"code": c, "name": n, "src": ["대표 종목"]} for c, n in heroes.GLOBAL_POOL[market]]
    b = heroes.board(pool, workers=6, market=market)
    return {"kind": "hero", "asof": bot.now().strftime("%Y-%m-%d %H:%M"), "took": round(time.time() - t0, 1),
            "principles": heroes.PRINCIPLES, "heroes": [{"key": k, "name": n, "icon": i, "theme": th, "motto": m}
                                                        for k, n, i, th, m in heroes.HEROES], **b}


PICKS = {"hero_us": (lambda: picks_hero_global("us"), 12 * 3600), "hero_eu": (lambda: picks_hero_global("eu"), 12 * 3600),
         "hero_cn": (lambda: picks_hero_global("cn"), 12 * 3600), "hero_jp": (lambda: picks_hero_global("jp"), 12 * 3600),
         "hero": (picks_hero, 6 * 3600), "surge": (picks_surge, 900), "value": (picks_value, 3600), "ackman": (picks_ackman, 3600)}


def picks(kind):
    fn, ttl = PICKS.get(kind, PICKS["hero"])
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
    try:                                          # 🏛️ 영웅 5인 체크 (이미 받은 데이터로 계산 — 추가 요청 없음)
        import heroes
        out = {**out, "heroes": heroes.score(out)}
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
    for kind, label in (("hero", "🏛️ 영웅"), ("surge", "🚀 급등 후보"), ("value", "💎 가치주"), ("ackman", "🇺🇸 애크먼")):
        p = _cache.get("picks:" + kind)
        if p and isinstance(p[1], dict):
            for x in p[1].get("items", []):
                if (x.get("code") or x.get("t")) == it["code"]:
                    tags.append(f"{label} {x.get('rank') or ''}{'위' if x.get('rank') else ''}".strip())
                    if kind == "value" and x.get("held"):
                        tags.append("📌 내 계좌 보유")
    return {**out, "tags": tags}


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
                    k, dd = (qs.get("k") or ["surge"])[0], (qs.get("d") or [""])[0]
                    if k == "surge" and re.fullmatch(r"\d{4}-\d{2}-\d{2}", dd):
                        out = cached("picks:surge:" + dd, 900, lambda: picks_surge(dd))
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
                d = data()
                role, why = role_info(self.client_address[0])
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
        self._send(200, open(fp, "rb").read(), ctype)

    def do_POST(self):
        if not self._auth():
            return
        if role_of(self.client_address[0]) == "viewer":   # 보기 전용은 아무것도 바꿀 수 없음
            return self._send(403, json.dumps({"error": "보기 전용"}, ensure_ascii=False), "application/json; charset=utf-8")
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
    threading.Thread(target=intraday_loop, daemon=True).start()
    ThreadingHTTPServer((host, port), H).serve_forever()
