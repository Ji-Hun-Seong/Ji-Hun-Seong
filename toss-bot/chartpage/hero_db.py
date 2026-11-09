"""
hero_db.py — 🏛️ 대가 10인 채점 데이터베이스 (SQLite, state/heroes.db)

왜: 코스피 전체 + 해외 전체(시총 기준 이상)는 수천 종목 → 화면을 열 때 계산하면 몇십 분.
    그래서 서버 뒤에서 일꾼(worker)이 쉬지 않고 '가장 오래된 점수'부터 다시 채점해 DB에 한 줄씩 저장하고,
    화면은 DB에 있는 점수를 바로 읽기만 한다 (기다림 없음). 새 종목은 채점되는 대로 목록에 하나씩 늘어남.

표
  stocks  (market, code)  종목 목록 — 이름·시총(억원)·출처·우선순위·내 보유·활성 여부
  scores  (market, code)  마지막 채점 결과 한 줄(JSON)·채점 시각·성공 여부
  meta    (k)             목록 갱신 시각 등

갱신 주기
  종목 목록   : 7일마다 (코스피=네이버 시총 순, 해외=야후 스크리너 나라별 시총 순) · 내 계좌·아는 회사는 6시간마다
  점수        : 20시간 지난 것부터 다시 (매일 한 바퀴) — 재무·공시는 heroes._disk / dart_fin 디스크 저장본을 재사용,
                매일 새로 받는 건 시세·밸류(PER 등)뿐
  최소 시총   : 한국 2,000억 · 해외 2조원(약 14억 달러) — 이보다 작으면 세력 장난에 휘둘리기 쉬워 제외
                (단 내 계좌·아는 회사·가치주 후보는 크기와 상관없이 포함)
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor

MIN_KR_EOK = float(os.environ.get("HERO_MIN_KR_EOK", "2000"))      # 한국 최소 시총(억원)
MIN_GL_EOK = float(os.environ.get("HERO_MIN_GL_EOK", "20000"))     # 해외 최소 시총(억원) ≈ $1.4B
STALE = 20 * 3600                                                  # 이보다 오래된 점수는 다시 채점
UNI_EVERY = 7 * 86400
EXTRA_EVERY = 6 * 3600
MARKETS = ["kr", "us", "eu", "cn", "jp"]
# 야후 스크리너 지역 → 그 나라 '본 거래소' 심볼만 (같은 회사가 여러 거래소에 중복되는 것 방지)
REGIONS = {
    "us": [("us", r"^[A-Z][A-Z\-]{0,5}$")],
    "eu": [("gb", r"\.L$"), ("de", r"\.DE$"), ("fr", r"\.PA$"), ("nl", r"\.AS$"), ("ch", r"\.SW$"), ("it", r"\.MI$"),
           ("es", r"\.MC$"), ("se", r"\.ST$"), ("dk", r"\.CO$"), ("no", r"\.OL$"), ("fi", r"\.HE$"), ("be", r"\.BR$"),
           ("at", r"\.VI$"), ("ie", r"\.IR$"), ("pt", r"\.LS$")],
    "cn": [("cn", r"\.(SS|SZ)$"), ("hk", r"\.HK$")],
    "jp": [("jp", r"\.T$")],
}
# 미국은 정식 거래소만 (장외 OTC·핑크시트에 올라온 외국 회사 GDR — 예: SK hynix — 제외)
US_EXCH = {"NMS", "NGM", "NCM", "NYQ", "ASE", "PCX", "BTS", "NYS", "NAS"}
UNI_VER = "2"                                                       # 목록 규칙이 바뀌면 올림 → 7일 안 기다리고 바로 다시 받음
ROW_VER = "3"                                                       # 채점 줄에 새 칸이 생기면 올림 → 20시간 안 기다리고 다시 채점
PRIO = {"내 계좌": 0, "아는 회사": 1, "가치주 후보": 2, "대표 종목": 3}

PATH = None
_local = threading.local()
status = {"running": False}


def init(path: str):
    global PATH
    PATH = path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    c = db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS stocks(market TEXT, code TEXT, name TEXT, mcap_eok REAL, ccy TEXT, src TEXT DEFAULT '[]',
        corp_code TEXT, prio INTEGER DEFAULT 5, held INTEGER DEFAULT 0, active INTEGER DEFAULT 1, seen REAL,
        PRIMARY KEY(market, code));
    CREATE TABLE IF NOT EXISTS scores(market TEXT, code TEXT, scored REAL, ok INTEGER, row TEXT, PRIMARY KEY(market, code));
    CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
    CREATE INDEX IF NOT EXISTS i_scores ON scores(market, scored);
    """)
    c.commit()


def db() -> sqlite3.Connection:
    c = getattr(_local, "c", None)
    if c is None:
        c = sqlite3.connect(PATH, timeout=30)
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        _local.c = c
    return c


def meta_get(k, default=None):
    r = db().execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
    return r[0] if r else default


def meta_set(k, v):
    db().execute("INSERT OR REPLACE INTO meta(k, v) VALUES(?, ?)", (k, str(v)))
    db().commit()


# ── 종목 목록 ────────────────────────────────────────
def _num(v):
    s = re.sub(r"[,\s원]", "", str(v or ""))
    try:
        return float(s)
    except ValueError:
        return None


def universe_kr() -> list[dict]:
    """코스피 보통주 중 시총 MIN_KR_EOK 이상 (네이버 시총 순 — 기준 밑으로 내려가면 멈춤)"""
    import requests
    out, seen = [], set()
    for page in range(1, 15):
        j = requests.get("https://m.stock.naver.com/api/stocks/marketValue/KOSPI", params={"page": page, "pageSize": 100},
                         headers={"User-Agent": "Mozilla/5.0"}, timeout=15).json()
        items = j.get("stocks", []) if isinstance(j, dict) else j
        if not items:
            break
        low = 0
        for it in items:
            c, n, mc = it.get("itemCode"), it.get("stockName") or "", _num(it.get("marketValue"))
            if mc is not None and mc < MIN_KR_EOK:
                low += 1
                continue
            if it.get("stockEndType") != "stock" or c in seen or not c.endswith("0") or re.search(r"스팩|\d+호$", n):
                continue                                   # ETF·리츠·우선주(코드 끝 0 아님)·스팩 제외
            seen.add(c)
            out.append({"code": c, "name": n, "mcap_eok": mc, "ccy": "KRW"})
        if low == len(items):                              # 이 페이지가 전부 기준 미달 → 끝
            break
    if len(out) < 200:
        raise RuntimeError(f"코스피 목록이 {len(out)}개뿐 — 네이버 응답 이상")
    try:
        import data_sources as ds
        cmap = {c["code"]: c.get("corp_code") for c in ds.load_corps()}
        for x in out:
            x["corp_code"] = cmap.get(x["code"])
    except Exception:
        pass
    return out


def _screen(region: str, offset: int, size: int = 250) -> list[dict]:
    import yfinance as yf
    q = yf.EquityQuery("eq", ["region", region])
    try:
        r = yf.screen(q, offset=offset, size=size, sortField="intradaymarketcap", sortAsc=False)
    except TypeError:                                      # 옛 yfinance
        r = yf.screen(q, offset=offset, size=size, sortField="intradaymarketcap", sortType="DESC")
    return (r or {}).get("quotes") or []


def universe_global(market: str) -> list[dict]:
    """야후 스크리너 — 나라별 시총 큰 순으로 받아 원화 환산 MIN_GL_EOK 밑으로 내려가면 멈춤"""
    import heroes
    out, seen = [], set()
    for region, pat in REGIONS[market]:
        for off in range(0, 5000, 250):
            qs = _screen(region, off)
            if not qs:
                break
            low = 0
            for q in qs:
                sym, ccy, mc = q.get("symbol") or "", q.get("currency"), q.get("marketCap")
                fx = heroes._krw_per(ccy) if ccy else None
                eok = mc * fx / 1e8 if mc and fx else None
                if eok is None or eok < MIN_GL_EOK:
                    low += 1
                    continue
                if q.get("quoteType", "EQUITY") != "EQUITY" or not re.search(pat, sym) or sym in seen:
                    continue
                if region == "us" and q.get("exchange") and q["exchange"] not in US_EXCH:
                    continue
                seen.add(sym)
                out.append({"code": sym, "name": q.get("longName") or q.get("shortName") or sym, "mcap_eok": eok, "ccy": ccy})
            if low >= len(qs) * 0.9:                       # 거의 다 기준 미달 → 이 나라 끝
                break
            time.sleep(1)
    if len(out) < 20:
        raise RuntimeError(f"{market} 목록이 {len(out)}개뿐 — 야후 스크리너 응답 이상")
    return out


_SUFFIX = re.compile(r"[,\s]+(the\s+)?(company\s+limited|co\.?,?\s*ltd\.?|corporation|corp\.?|incorporated|inc\.?|limited|ltd\.?|"
                     r"holdings?|group|plc|p\.l\.c\.|s\.?a\.?|n\.?v\.?|a\.?g\.?|se|ag|ab(\s*\(publ\))?|asa|oyj|spa|s\.p\.a\.|"
                     r"kabushiki kaisha|k\.k\.|class [a-c]|a/s|soci[ée]t[ée] europ[ée]enne)\.?$", re.I)


def short_name(n: str) -> str:
    """'Taiwan Semiconductor Manufacturing Company Limited' → 'Taiwan Semiconductor Manufacturing' (꼬리 법인명 떼기)"""
    n = (n or "").strip()
    for _ in range(3):
        m = _SUFFIX.sub("", n).strip(" ,.")
        if m == n or len(m) < 2:
            break
        n = m
    return n


def _upsert(market, x, src, active=1):
    c = db()
    r = c.execute("SELECT src, prio, held FROM stocks WHERE market=? AND code=?", (market, x["code"])).fetchone()
    srcs = json.loads(r[0]) if r and r[0] else []
    if src and src not in srcs:
        srcs.append(src)
    prio = min([PRIO.get(s, 5) for s in srcs] or [5])
    held = int(bool(x.get("held")) or (bool(r[2]) if r and src != "내 계좌" else False))
    c.execute("""INSERT INTO stocks(market, code, name, mcap_eok, ccy, src, corp_code, prio, held, active, seen)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?)
                 ON CONFLICT(market, code) DO UPDATE SET name=COALESCE(excluded.name, name), mcap_eok=COALESCE(excluded.mcap_eok, mcap_eok),
                   ccy=COALESCE(excluded.ccy, ccy), src=excluded.src, corp_code=COALESCE(excluded.corp_code, corp_code),
                   prio=excluded.prio, held=excluded.held, active=MAX(active, excluded.active), seen=excluded.seen""",
              (market, x["code"], x.get("name"), x.get("mcap_eok"), x.get("ccy"), json.dumps(srcs, ensure_ascii=False),
               x.get("corp_code"), prio, held, active, time.time()))


def refresh(market: str, extras_fn, force=False):
    """목록 갱신: 7일마다 전체(기준 미달·상폐는 비활성), 6시간마다 내 계좌·아는 회사만"""
    now = time.time()
    c = db()
    if force or now - float(meta_get("uni:" + market, 0)) > UNI_EVERY or meta_get("uni_ver:" + market) != UNI_VER:
        status["now"] = f"{market} 종목 목록 받는 중"
        base = universe_kr() if market == "kr" else universe_global(market)   # 실패하면 예외 → 기존 목록 유지
        c.execute("UPDATE stocks SET active=0, src='[]', prio=5 WHERE market=?", (market,))
        for x in base:
            _upsert(market, x, {"kr": "코스피"}.get(market, "시총 상위"))
        c.commit()
        meta_set("uni:" + market, now)
        meta_set("uni_ver:" + market, UNI_VER)
        meta_set("extra:" + market, 0)
    if now - float(meta_get("extra:" + market, 0)) > EXTRA_EVERY:
        c.execute("UPDATE stocks SET held=0 WHERE market=?", (market,))
        for x in extras_fn(market):
            _upsert(market, x, x["src"], 1)
        c.commit()
        meta_set("extra:" + market, now)


# ── 채점 일꾼 ─────────────────────────────────────────
#   스레드 3개: ① 종목 목록(느린 해외 스크리너가 채점을 막지 않게 따로) ② 한국 채점 ③ 해외 채점(야후 제한에 걸려도 한국은 계속)
def stale(markets, limit=40):
    """아직 안 했거나 오래된 것부터 — 시장마다 번갈아(시장 안에서는 내 계좌·아는 회사 → 시총 큰 순)"""
    cut = time.time() - STALE
    ph = ",".join("?" * len(markets))
    return db().execute(f"""SELECT market, code, name, corp_code, src, held FROM (
        SELECT s.market, s.code, s.name, s.corp_code, s.src, s.held, (c.scored IS NOT NULL) AS done,
               ROW_NUMBER() OVER (PARTITION BY s.market, (c.scored IS NOT NULL) ORDER BY s.prio, s.mcap_eok DESC) AS rn
        FROM stocks s LEFT JOIN scores c ON c.market=s.market AND c.code=s.code
        WHERE s.active=1 AND s.market IN ({ph}) AND (c.scored IS NULL OR c.scored < ?))
        ORDER BY done, rn LIMIT ?""", (*markets, cut, limit)).fetchall()


def _score_one(r):
    import heroes
    market, code, name, corp, src, held = r
    p = {"code": code, "name": name, "corp_code": corp, "src": json.loads(src or "[]"), "held": bool(held)}
    return market, code, heroes.board_row(p, market)


def universe_loop(extras_fn):
    while True:
        for m in MARKETS:                                   # 한국 먼저
            try:
                refresh(m, extras_fn)
                status.pop("uni_error:" + m, None)
            except Exception as e:
                status["uni_error:" + m] = f"{m} 목록: {type(e).__name__}: {str(e)[:120]}"
                meta_set("uni:" + m, time.time() - UNI_EVERY + 3600)         # 1시간 뒤 다시 시도
        time.sleep(600)


def score_loop(group, markets, workers):
    while True:
        try:
            batch = stale(markets, 30)
            if not batch:
                status[group] = "다 최신 — 쉬는 중"
                time.sleep(300)
                continue
            status[group] = f"채점 중 ({batch[0][2]} …)"
            throttled = False
            with ThreadPoolExecutor(workers) as ex:
                for market, code, row in ex.map(_score_one, batch):
                    err = row.get("error") or ""
                    if re.search(r"Too Many|429|Rate", err, re.I):
                        throttled = True
                        continue
                    ok = int(not err and row.get("total") is not None)
                    t = time.time() if ok else time.time() - STALE + 3 * 3600   # 실패는 3시간 뒤 다시
                    db().execute("INSERT OR REPLACE INTO scores(market, code, scored, ok, row) VALUES(?,?,?,?,?)",
                                 (market, code, t, ok, json.dumps(row, ensure_ascii=False, default=str)))
                    db().commit()                                               # 한 종목씩 바로 화면에 보이게
            status.pop(group + "_error", None)
            if throttled:
                status[group] = "야후 요청 제한 — 2분 쉼"
                time.sleep(120)
        except Exception as e:
            status[group + "_error"] = f"{type(e).__name__}: {str(e)[:160]}"
            time.sleep(60)


def start(extras_fn):
    status["running"] = True
    if meta_get("row_ver") != ROW_VER:                                  # 화면의 기존 점수는 그대로 두고 '다시 할 차례'로만 표시
        db().execute("UPDATE scores SET scored = MIN(scored, ?) WHERE ok=1", (time.time() - STALE - 1,))
        db().commit()
        meta_set("row_ver", ROW_VER)
    threading.Thread(target=universe_loop, args=(extras_fn,), daemon=True).start()
    threading.Thread(target=score_loop, args=("kr", ["kr"], 4), daemon=True).start()
    threading.Thread(target=score_loop, args=("gl", ["us", "eu", "cn", "jp"], 3), daemon=True).start()


# ── 한국 업종·주요제품 (GitHub Actions 가 매주 만드는 toss-bot/data/industry_kr.csv, 하루 캐시) ──
_IND = {"t": 0, "map": {}}


def industry_kr() -> dict:
    if time.time() - _IND["t"] < 86400 and _IND["map"]:
        return _IND["map"]
    import csv, io
    text = None
    try:
        import requests
        r = requests.get("https://raw.githubusercontent.com/Ji-Hun-Seong/Ji-Hun-Seong/main/toss-bot/data/industry_kr.csv", timeout=10)
        r.raise_for_status()
        text = r.text
    except Exception:
        f = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "industry_kr.csv")
        if os.path.exists(f):
            text = open(f, encoding="utf-8").read()
    if text:
        m = {}
        for x in csv.DictReader(io.StringIO(text)):
            m[x["code"]] = {"sector": x.get("sector") or "", "product": x.get("product") or ""}
        _IND.update(t=time.time(), map=m)
    else:
        _IND["t"] = time.time() - 86400 + 600                 # 못 받으면 10분 뒤 다시
    return _IND["map"]


# ── 화면용 읽기 (바로 응답) ─────────────────────────────
def screen(market: str) -> dict:
    """🔎 재무 필터 — 종목별 숫자만 가볍게. 조건 계산은 화면에서 (입력할 때마다 바로 반영)"""
    if market not in MARKETS:
        market = "kr"
    rows = db().execute("""SELECT c.row, s.mcap_eok, s.market FROM scores c JOIN stocks s ON s.market=c.market AND s.code=c.code
                           WHERE c.market=? AND s.active=1 AND c.ok=1""", (market,)).fetchall()
    ind = industry_kr() if market == "kr" else {}
    pos = lambda v: v if isinstance(v, (int, float)) and v > 0 else None   # PER·PBR 음수(적자·자본잠식)는 '10 미만'에 걸리면 안 됨
    items, n_fin = [], 0
    for row, mc, _ in rows:
        x = json.loads(row)
        f = x.get("fin") or {}
        n_fin += bool(f)
        i = ind.get(x.get("code"))
        items.append({**f, "c": x["code"], "n": x["name"] if market == "kr" else short_name(x.get("name")), "u": market != "kr",
                      "ind": (i or {}).get("sector") or x.get("industry"), "per": pos(x.get("per")), "pbr": pos(x.get("pbr")),
                      "dy": x.get("yield"), "mc": round(x.get("mcap_eok") or mc or 0) or None})
    return {"market": market, "items": items, "n_fin": n_fin, "min_eok": MIN_KR_EOK if market == "kr" else MIN_GL_EOK}


def board(market: str) -> dict:
    import heroes
    c = db()
    rows = c.execute("""SELECT c.row, s.src, s.held, s.mcap_eok, c.ok FROM scores c JOIN stocks s ON s.market=c.market AND s.code=c.code
                        WHERE c.market=? AND s.active=1""", (market,)).fetchall()
    items = []
    ind = industry_kr() if market == "kr" else {}
    for row, src, held, mc, ok in rows:
        x = json.loads(row)
        i = ind.get(x.get("code"))
        if i:                                                   # 한국: KRX 업종 + 주요제품
            x["industry"], x["product"] = i["sector"] or x.get("industry"), i["product"]
        x["src"], x["held"] = json.loads(src or "[]"), bool(held)
        if market != "kr":
            x["name"] = short_name(x.get("name"))
        if x.get("mcap_eok") is None:
            x["mcap_eok"] = mc
        items.append(x)
    n_pool = c.execute("SELECT COUNT(*) FROM stocks WHERE market=? AND active=1", (market,)).fetchone()[0]
    fresh = c.execute("""SELECT COUNT(*), MIN(c.scored), MAX(c.scored) FROM scores c JOIN stocks s ON s.market=c.market AND s.code=c.code
                         WHERE c.market=? AND s.active=1 AND c.scored >= ?""", (market, time.time() - STALE)).fetchone()
    out = heroes.aggregate(items, n_pool, market)
    last = c.execute("SELECT MAX(scored) FROM scores WHERE market=? AND ok=1", (market,)).fetchone()[0]
    uni = float(meta_get("uni:" + market, 0) or 0)
    out.update({"kind": "hero", "principles": heroes.PRINCIPLES, "heroes": heroes.hero_meta(),
                "asof": time.strftime("%m-%d %H:%M", time.localtime(last)) if last else "채점 전",
                "progress": {"scored": len(items), "fresh": fresh[0], "pool": n_pool,
                             "worker": status.get("kr" if market == "kr" else "gl") or "시작 중",
                             "error": status.get("uni_error:" + market) or status.get(("kr" if market == "kr" else "gl") + "_error"), "universe_at": time.strftime("%m-%d", time.localtime(uni)) if uni else None},
                "min_eok": MIN_KR_EOK if market == "kr" else MIN_GL_EOK})
    return out
