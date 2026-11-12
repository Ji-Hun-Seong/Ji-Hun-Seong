"""🔌 토스봇 MCP 서버 — Claude 앱에서 대화로 토스봇 데이터를 조회 (조회 전용, 주문 도구 없음)

  · 대시보드(dashboard.py, localhost:8080)의 API를 읽어 AI가 쓰기 좋은 크기로 줄여서 돌려줌
  · MCP 'Streamable HTTP' 방식을 표준 라이브러리로 직접 구현 (pip 설치 필요 없음)
  · 주소: https://<서버>.ts.net/<MCP_SECRET>/mcp  — Tailscale Funnel 로 이 주소 하나만 인터넷에 열고,
          비밀 경로(MCP_SECRET, .env)를 모르면 404. 주문·긴급 정지 같은 쓰기 기능은 아예 없음
  · 설치: bash setup/mcp.sh  (비밀 경로 만들기 → 상시 실행 서비스 → Funnel 열기 → 연결 주소 출력)

도구: market_surge · hero_rank · java_picks · etf_rank · my_fund · stock · news_radar
"""
from __future__ import annotations

import base64
import json
import re
import os
import sys
import urllib.parse
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")


def load_env():
    p = os.path.join(HERE, ".env")
    if os.path.exists(p):
        for ln in open(p, encoding="utf-8"):
            if "=" in ln and not ln.lstrip().startswith("#"):
                k, v = ln.split("=", 1)
                os.environ.setdefault(k.strip(), v.split(" #")[0].strip().strip('"').strip("'"))


load_env()
DASH = os.environ.get("MCP_DASH_URL", f"http://127.0.0.1:{os.environ.get('DASH_PORT', '8080')}")
SECRET = os.environ.get("MCP_SECRET", "").strip()
PORT = int(os.environ.get("MCP_PORT", "8765"))


# ── 대시보드 API 읽기 ─────────────────────────────────────────────
def dash(path: str, timeout: int = 60) -> dict:
    req = urllib.request.Request(DASH + path)
    pw = os.environ.get("DASH_PASSWORD")
    if pw:
        req.add_header("Authorization", "Basic " + base64.b64encode(f"mcp:{pw}".encode()).decode())
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def trim(x, limit=20, depth=0):
    """AI에 넘기기 좋게: 목록은 limit개, 긴 글은 400자, 너무 깊은 건 생략"""
    if depth > 5:
        return "…"
    if isinstance(x, dict):
        return {k: trim(v, limit, depth + 1) for k, v in x.items() if v not in (None, "", [], {})}
    if isinstance(x, list):
        return [trim(v, limit, depth + 1) for v in x[:limit]] + ([f"…외 {len(x) - limit}개"] if len(x) > limit else [])
    if isinstance(x, str) and len(x) > 400:
        return x[:400] + "…"
    if isinstance(x, float):
        return round(x, 3)
    return x


def pick(d: dict, keys) -> dict:
    return {k: d[k] for k in keys if k in d and d[k] not in (None, "", [], {})}


# ── 도구 ─────────────────────────────────────────────
def t_market_surge(date: str = "", limit: int = 15):
    q = "/api/picks?k=surge" + (f"&d={urllib.parse.quote(date)}" if date else "")
    d = dash(q)
    if d.get("error"):
        return d
    out = pick(d, ("date", "method", "n_scored", "grade", "context"))
    out["후보(다음 날 급등 가능성 순)"] = d.get("items", [])
    out["그날 실제 급등주"] = d.get("surgers")
    out["장중 지금"] = d.get("live")
    return trim(out, limit)


def t_hero_rank(market: str = "kr", style: str = "value", limit: int = 20):
    market = market if market in ("kr", "us", "eu", "cn", "jp") else "kr"
    d = dash("/api/picks?k=" + ("hero" if market == "kr" else "hero_" + market))
    if d.get("error"):
        return d
    key = "growth" if style == "growth" else "value"
    xs = [x for x in d.get("items", []) + (d.get("more") or []) if x.get(key) is not None]
    try:                                              # 앱 💎/🚀 탭과 같은 걸러내기 (PBR·PER·버핏/린치 점수·매출·순이익 꾸준히 증가·장기 부적합 제외)
        sys.path.insert(0, os.path.join(HERE, "chartpage"))
        import fund_sim as F
        m = "kr" if market == "kr" else "us"
        xs = [x for x in xs if (F.is_growth(x, m) if key == "growth" else F.is_value(x, m))]
    except Exception:
        pass
    xs.sort(key=lambda x: -(x.get(key) or 0))
    rows = []
    for x in xs[:limit]:
        r = pick(x, ("code", "name", "industry", "about", "lynch_cat", "per", "pbr", "yield", "mcap_eok", "value", "growth", "style", "held", "best", "worst"))
        g = x.get("grade")
        if isinstance(g, dict):
            r["grade"] = g.get("label")
        rows.append(r)
    return trim({"market": market, "style": key, "asof": d.get("asof") or d.get("date"), "items": rows,
                 "설명": "대가(버핏·린치·그레이엄 등) 원칙 점수. held=내 계좌 보유"}, limit)


def t_java_picks(limit: int = 20):
    d = dash("/api/picks?k=value")
    return trim(d, limit)


def t_etf_rank(category: str = "all", sort: str = "mom", limit: int = 20):
    d = dash("/api/picks?k=etf", timeout=90)
    if d.get("error") or d.get("empty"):
        return trim({k: d.get(k) for k in ("error", "status", "hist_days", "has_key")})
    xs = d.get("items", [])
    if category == "tdf":                       # TDF는 목표연도별로 지수가 달라 전부(대표+나머지) 보여 줌
        xs = [x for x in xs + d.get("more", []) if "TDF" in (x.get("name") or "").upper()]
    elif category == "active":
        xs = [x for x in xs if x.get("active")]
    elif category == "all":
        xs = [x for x in xs if x.get("cat") != "lev"]
    else:
        xs = [x for x in xs if x.get("cat") == category]
    sort = sort if sort in ("mom", "r12", "r36", "r3", "r6", "r1", "eff") else "mom"
    xs = sorted([x for x in xs if x.get(sort) is not None], key=lambda x: -x[sort])[:limit]
    keys = ("code", "name", "cat", "active", "hedge", "idx", "net_eok", "disc", "r1", "r3", "r6", "r12", "r36", "mom", "vol", "mdd", "ex12", "sibs", "fee", "fee_min", "cheap")
    return trim({"asof": d.get("asof"), "bench": d.get("bench"), "backtest": d.get("bt"), "items": [pick(x, keys) for x in xs],
                 "설명": "수익률 %(가격 기준, 분배금 제외). mom=3·6·12개월 평균, mdd=1년 최대 낙폭, ex12=KODEX200 대비 1년, net_eok=순자산 억원"}, limit)


def t_my_fund():
    d = dash("/api/picks?k=fund")
    m = d.get("mine") or {}
    if m.get("hist"):
        m["hist"] = m["hist"][-20:]
    us = [pick(f, ("name", "ret", "bench_ret", "inception")) for f in d.get("funds", [])]
    return trim({"내 펀드(실제 계좌)": m, "미국 모의 펀드": us,
                 "설명": "기준가 1000에서 시작, 산 돈=설정·판 돈=환매로 처리한 시간가중수익률. bench=코스피(설정일=1000)"}, 30)


def t_stock(query: str):
    d = dash("/api/stock?q=" + urllib.parse.quote(query), timeout=90)
    if not d.get("error"):                            # 사업요약·매출비중은 따로 받음 (앱과 같은 방식)
        try:
            d.update({k: v for k, v in dash("/api/stock-extra?q=" + urllib.parse.quote(d.get("code") or query)
                                             + ("&us=1" if d.get("us") else ""), timeout=90).items() if v})
        except Exception:
            pass
    return trim(d, 12)


def t_news_radar(limit: int = 15):
    d = dash("/api/radar", timeout=60)
    if d.get("loading"):
        return {"loading": True, "msg": "서버가 오늘·어제 공시와 뉴스를 확인하는 중 — 1~2분 뒤 다시 물어보세요"}
    return trim(d, limit)


# ── 🌐 공개 소개 페이지 (조회 전용) ─────────────────────────────
# https://<Funnel 주소>/ 로 누구나 볼 수 있는 페이지. 계좌 금액·주수·매매내역·주문 기능은 아예 보내지 않음.
# 글은 public/profile.json 에서 고침. 데이터는 10분 캐시.
import threading
import time
PUB_DIR = os.path.join(HERE, "public")
_pub = {"t": 0.0, "d": None}
_pub_lock = threading.Lock()


def _thin(hist, n=260):
    """그래프용으로 점 개수 줄이기"""
    if len(hist) <= n:
        return hist
    k = len(hist) / n
    return [hist[int(i * k)] for i in range(n)] + [hist[-1]]


def pub_data() -> dict:
    out, errs = {}, {}
    try:
        with open(os.path.join(PUB_DIR, "profile.json"), encoding="utf-8") as f:
            prof = json.load(f)
    except Exception as e:
        prof, errs["profile"] = {}, str(e)[:120]
    out["profile"] = {k: v for k, v in prof.items() if not k.startswith("_")}
    try:
        sys.path.insert(0, os.path.join(HERE, "chartpage"))
        import heroes
        P = heroes.PRINCIPLES
        out["principles"] = {"mix": P["mix"]["text"], "iron": P["iron"], "portfolio": P["portfolio"],
                             "rules": [{"who": w, "title": t, "text": x} for w, t, x in P["rules"]]}
        out["heroes"] = [pick(h, ("name", "icon", "motto", "style")) for h in heroes.hero_meta()]
    except Exception as e:
        errs["principles"] = f"{type(e).__name__}: {str(e)[:120]}"
    ranks = {}
    for m in ("kr", "us"):
        for sty in ("value", "growth"):
            try:
                r = t_hero_rank(m, sty, 10)
                ranks[f"{m}_{sty}"] = {"asof": r.get("asof"), "items": [pick(x, ("name", "code", "industry", "about", "per", "pbr", "yield", sty, "grade"))
                                                                     for x in r.get("items", []) if isinstance(x, dict)]}
            except Exception as e:
                errs[f"rank_{m}_{sty}"] = f"{type(e).__name__}: {str(e)[:120]}"
    out["ranks"] = ranks
    try:
        d = dash("/api/picks?k=fund")
        out["funds"] = [{**pick(f, ("name", "desc", "inception", "market", "bench_name", "ret", "bench_ret")),
                         "hist": _thin(f.get("hist") or []),
                         "holdings": [pick(h, ("name", "weight")) for h in (f.get("holdings") or [])[:10]]}
                        for f in d.get("funds", [])]
        m = d.get("mine") or {}
        if prof.get("show_my_fund", True) and m.get("hist"):   # 내 계좌: 기준가·수익률만 (금액·종목·주수·매매내역 없음)
            out["mine"] = {**pick(m, ("inception", "ret", "bench_ret")), "hist": _thin(m["hist"])}
    except Exception as e:
        errs["funds"] = f"{type(e).__name__}: {str(e)[:120]}"
    out["updated"] = time.strftime("%Y-%m-%d %H:%M")
    if errs:
        out["errors"] = errs
    return out


def pub_cached() -> dict:
    with _pub_lock:
        if not _pub["d"] or time.time() - _pub["t"] > 600:
            _pub["d"], _pub["t"] = pub_data(), time.time()
        return _pub["d"]



# ── 📱 공개 앱 (/app/) — 대시보드 화면을 그대로, 보기 전용으로 ─────────────
# https://<Funnel 주소>/app/ 에서 누구나 대시보드와 똑같은 화면(종목 검색·차트·수급·재무·밸류·공시·리포트·발굴·감시·자동·펀드)을 씀.
# · 대시보드에 'X-Toss-Public: 1' 을 붙여 넘겨서 항상 👀 보기 전용 → 계좌 탭·긴급 정지·주문 화면이 숨겨짐
# · 아래 목록에 있는 '읽기' 주소만 넘기고, 주문·체결내역·예약·실시간 호가 스트림·POST 는 아예 안 넘김(404/403)
# · 내 펀드는 소개 페이지 약속대로 기준가·수익률만 (보유 종목·매매내역 빼고, profile.json show_my_fund=false 면 통째로 숨김)
PUB_STATIC = {"", "index.html", "kchart.js", "icons.js", "manifest.json", "icon-180.png", "icon-512.png", "chart.umd.min.js",
              "masterroad/index.html", "masterroad/data1.js", "masterroad/data2.js", "masterroad/data3.js",
              "fundrule/index.html", "fundrule/data.js", "fundrule/data2.js", "fundrule/data4.js",
              "fundroad/index.html", "fundroad/data.js", "fundroad/quiz.js", "deep.js"}
PUB_DEEP = re.compile(r"^(?:(?:fundroad|masterroad)/deep/(?:index|topics/[\w-]+)\.json"   # 매일 쌓이는 심화 글
                      r"|(?:fundroad|masterroad)/dict/terms\.json|dict\.js|bondcalc\.js"        # 백과·채권 계산기
                      r"|jamunpass/(?:index\.html|[\w-]+\.js))$")                                # 자문패스
PUB_API = {"/api/data", "/api/radar", "/api/scan", "/api/stock", "/api/stock-extra", "/api/picks", "/api/search",
           "/api/chart", "/api/fin", "/api/screen", "/api/popular", "/api/doc", "/api/orderbook", "/api/mini", "/api/dividend"}
PUB_BLOCKED = {"/api/trade", "/api/fills", "/api/reserve", "/api/ob-stream", "/api/order", "/api/stop"}
_pub_sem = threading.BoundedSemaphore(int(os.environ.get("PUB_MAX_CONC", "12")))   # 한꺼번에 몰려도 서버가 버티게
_ob_cache = {}                                    # 호가: 같은 종목은 3초 동안 같은 답 (토스 API 아끼기)


def _show_my_fund() -> bool:
    try:
        with open(os.path.join(PUB_DIR, "profile.json"), encoding="utf-8") as f:
            return json.load(f).get("show_my_fund", True) is not False
    except Exception:
        return True


def pub_proxy(rest: str, query: str):
    """(상태코드, 본문, content-type, cache-control) — rest 는 /app/ 뒤 경로"""
    rest = rest.lstrip("/")
    api = "/" + rest if rest.startswith("api/") else None
    if api is None and rest not in PUB_STATIC and not PUB_DEEP.match(rest):
        return 404, b"not found", "text/plain", None
    if api is not None:
        if api in PUB_BLOCKED:
            return 403, json.dumps({"error": "공개 화면에서는 쓸 수 없는 기능이에요 (주문·체결·예약)"}, ensure_ascii=False).encode(), "application/json; charset=utf-8", None
        if api not in PUB_API:
            return 404, b"not found", "text/plain", None
    query = urllib.parse.quote(query, safe="=&%+")    # 브라우저가 안 바꾼 한글 등도 안전하게
    url = DASH + "/" + (rest if rest != "index.html" else "") + ("?" + query if query else "")
    ck = None
    if api == "/api/orderbook":
        ck = query
        hit = _ob_cache.get(ck)
        if hit and time.time() - hit[0] < 3:
            return 200, hit[1], "application/json; charset=utf-8", "no-store"
    if not _pub_sem.acquire(timeout=20):
        return 503, json.dumps({"error": "지금 사람이 많아요 — 잠시 뒤 다시 시도"}, ensure_ascii=False).encode(), "application/json; charset=utf-8", None
    try:
        req = urllib.request.Request(url, headers={"X-Toss-Public": "1"})
        pw = os.environ.get("DASH_PASSWORD")
        if pw:
            req.add_header("Authorization", "Basic " + base64.b64encode(f"public:{pw}".encode()).decode())
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                code, body = r.status, r.read()
                ctype, cache = r.headers.get("Content-Type") or "application/octet-stream", r.headers.get("Cache-Control")
        except urllib.error.HTTPError as e:
            code, body, ctype, cache = e.code, e.read(), e.headers.get("Content-Type") or "text/plain", None
        except Exception as e:
            code, ctype, cache = 502, "application/json; charset=utf-8", None
            body = json.dumps({"error": f"대시보드 연결 실패 — {type(e).__name__}"}, ensure_ascii=False).encode()
    finally:
        _pub_sem.release()
    if api == "/api/picks" and "k=fund" in query and code == 200:
        try:
            d = json.loads(body.decode("utf-8"))
            m = d.get("mine")
            if isinstance(m, dict):
                if not _show_my_fund():
                    d["mine"] = {"empty": True, "note": "공개 화면에서는 내 계좌 펀드를 보여 주지 않아요"}
                elif not m.get("empty"):
                    d["mine"] = {**{k: v for k, v in m.items() if k not in ("holdings", "trades", "divs")}, "public": True}
            body = json.dumps(d, ensure_ascii=False, default=str).encode("utf-8")
        except Exception:
            pass
    if api == "/api/data" and code == 200:          # 혹시 몰라 한 번 더: 계좌·비율은 공개 화면에 절대 안 보냄
        try:
            d = json.loads(body.decode("utf-8"))
            d.update(account={"hidden": True}, mix={"hidden": True}, viewer=True, public=True)
            body = json.dumps(d, ensure_ascii=False, default=str).encode("utf-8")
        except Exception:
            pass
    if ck is not None and code == 200:
        _ob_cache[ck] = (time.time(), body)
        if len(_ob_cache) > 500:
            _ob_cache.clear()
    if rest == "manifest.json" and code == 200:   # 홈 화면에 추가하면 /app/ 으로 열리게
        try:
            mf = json.loads(body.decode("utf-8"))
            mf.update(start_url="/app/", scope="/app/")
            body = json.dumps(mf, ensure_ascii=False).encode("utf-8")
        except Exception:
            pass
    return code, body, ctype, cache


S = lambda **p: {"type": "object", "properties": p, "additionalProperties": False}
TOOLS = {
    "market_surge": (t_market_surge, "한국 급등주: 다음 날 급등 후보 순위, 그날 실제 급등주와 재료, 장중 지금 막 오르기 시작한 종목. 날짜를 주면 그날 기준.",
                     S(date={"type": "string", "description": "YYYY-MM-DD (비우면 최신)"}, limit={"type": "integer", "default": 15})),
    "hero_rank": (t_hero_rank, "대가 투자원칙(버핏·린치·그레이엄·피셔·템플턴 등) 점수로 고른 종목 순위 — 앱 발굴 탭과 같은 걸러내기(가치: PBR 한국2/해외10 이하·PER 한국10/해외30 이하·버핏 10점↑, 성장: PBR 0~10·린치 10점↑·이익성장 10%↑·PEG 2↓·ROE 10%↑·저성장주/자산주 제외, 둘 다 매출·순이익 꾸준히 증가·장기 부적합 제외). 시장(kr/us/eu/cn/jp)과 스타일(value 가치/growth 성장).",
                  S(market={"type": "string", "enum": ["kr", "us", "eu", "cn", "jp"], "default": "kr"},
                    style={"type": "string", "enum": ["value", "growth"], "default": "value"}, limit={"type": "integer", "default": 20})),
    "java_picks": (t_java_picks, "자바 매매일지 DNA 20선: 실제 매매일지에서 뽑은 성향(업종·가격대·배당·재무)에 가장 잘 맞는 코스피 종목.",
                   S(limit={"type": "integer", "default": 20})),
    "etf_rank": (t_etf_rank, "국내 상장 ETF 수익률 순위 (KRX 일별 데이터). 분류와 정렬 선택, 과거 검증(상위 10개 vs KODEX 200) 포함. tdf=은퇴연도별 TDF만.",
                 S(category={"type": "string", "enum": ["all", "kr", "foreign", "bond", "tdf", "cmdty", "active", "lev"], "default": "all"},
                   sort={"type": "string", "enum": ["mom", "r12", "r36", "r3", "r6", "r1", "eff"], "default": "mom"},
                   limit={"type": "integer", "default": 20})),
    "my_fund": (t_my_fund, "내 펀드: 토스 실제 계좌를 공모펀드처럼 기준가로 산출한 성과(코스피 대비), 보유 종목 비중·수익률, 최근 체결. 미국 모의 펀드 요약 포함.", S()),
    "stock": (t_stock, "종목 상세: 시세·이동평균·수급·재무·공시·밸류. 한국은 이름이나 6자리 코드, 해외는 티커나 이름.",
              {**S(query={"type": "string", "description": "종목명 또는 코드 (예: 삼성전자, 005930, AAPL)"}), "required": ["query"]}),
    "news_radar": (t_news_radar, "뉴스·공시 레이더: 오늘·어제 공시와 뉴스 중 주가에 영향이 클 만한 것(수주·실적·자사주 등) 순위.",
                   S(limit={"type": "integer", "default": 15})),
}


def call_tool(name: str, args: dict) -> dict:
    if name not in TOOLS:
        return {"content": [{"type": "text", "text": f"없는 도구: {name}"}], "isError": True}
    fn = TOOLS[name][0]
    try:
        args = {k: v for k, v in (args or {}).items() if v not in (None, "")}
        if "limit" in args:
            args["limit"] = max(1, min(int(args["limit"]), 50))
        res = fn(**args)
        txt = json.dumps(res, ensure_ascii=False, default=str)
        if len(txt) > 60000:
            txt = txt[:60000] + "…(잘림)"
        return {"content": [{"type": "text", "text": txt}], "isError": False}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"오류: {type(e).__name__}: {str(e)[:300]} (대시보드가 켜져 있는지 확인: systemctl status toss-dash)"}],
                "isError": True}


def handle(msg: dict):
    """JSON-RPC 한 건 → 응답(dict) 또는 None(알림)"""
    mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if mid is None:                                   # notifications/initialized 등
        return None
    if method == "initialize":
        want = params.get("protocolVersion")
        res = {"protocolVersion": want if want in PROTOCOLS else PROTOCOLS[0],
               "capabilities": {"tools": {"listChanged": False}},
               "serverInfo": {"name": "toss-bot", "title": "토스봇 (조회 전용)", "version": "1.0"},
               "instructions": "한국어 사용자의 개인 투자 대시보드 데이터. 조회 전용이며 주문 기능은 없음. 매수 추천이 아니라 데이터와 확률로 답할 것."}
    elif method == "tools/list":
        res = {"tools": [{"name": n, "description": d, "inputSchema": s, "annotations": {"readOnlyHint": True, "openWorldHint": False}}
                         for n, (_, d, s) in TOOLS.items()]}
    elif method == "tools/call":
        res = call_tool(params.get("name"), params.get("arguments") or {})
    elif method == "ping":
        res = {}
    elif method in ("resources/list", "prompts/list"):
        res = {method.split("/")[0]: []}
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"지원하지 않는 메서드: {method}"}}
    return {"jsonrpc": "2.0", "id": mid, "result": res}


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *a):
        sys.stderr.write("mcp %s %s\n" % (self.command, self.path.split("?")[0].replace(SECRET, "<secret>") if SECRET else self.path))

    def _ok_path(self):
        return SECRET and self.path.split("?")[0].rstrip("/") == f"/{SECRET}/mcp"

    def _send(self, code, body=b"", ctype="application/json", cache=None):
        self.send_response(code)
        if cache:
            self.send_header("Cache-Control", cache)
        if body:
            self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):                                 # 서버 → 클라이언트 스트림은 안 씀
        if self._ok_path():
            return self._send(405)
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):               # 🌐 공개 소개 페이지 (조회 전용)
            try:
                with open(os.path.join(PUB_DIR, "index.html"), "rb") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")
            except OSError:
                return self._send(404)
        if path == "/app":                            # 📱 공개 앱 — 끝에 / 가 있어야 상대 주소(api/…)가 /app/api/… 로 감
            self.send_response(301); self.send_header("Location", "/app/"); self.send_header("Content-Length", "0"); self.end_headers()
            return
        if path.startswith("/app/") or path == "/api/doc":   # 화면 안에서 /api/doc 만 절대 주소로 부름
            q = self.path.split("?", 1)[1] if "?" in self.path else ""
            code, body, ctype, cache = pub_proxy(path[len("/app/"):] if path.startswith("/app/") else "api/doc", q)
            return self._send(code, body, ctype, cache)
        if path == "/pub/data":
            try:
                body = json.dumps(pub_cached(), ensure_ascii=False, default=str).encode("utf-8")
            except Exception as e:
                body = json.dumps({"error": f"{type(e).__name__}: {str(e)[:120]}"}, ensure_ascii=False).encode("utf-8")
            return self._send(200, body, "application/json; charset=utf-8")
        self._send(404)

    def do_DELETE(self):
        self._send(405 if self._ok_path() else 404)

    def do_POST(self):
        if not self._ok_path():
            return self._send(404)
        n = int(self.headers.get("Content-Length") or 0)
        try:
            msg = json.loads(self.rfile.read(n).decode("utf-8"))
        except ValueError:
            return self._send(400, json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}).encode())
        out = [r for r in (handle(m) for m in msg) if r] if isinstance(msg, list) else handle(msg)
        if not out:
            return self._send(202)
        self._send(200, json.dumps(out, ensure_ascii=False).encode("utf-8"))


if __name__ == "__main__":
    if not SECRET or len(SECRET) < 20:
        sys.exit("MCP_SECRET(20자 이상)가 .env 에 없어요 — bash setup/mcp.sh 로 만드세요")
    host = os.environ.get("MCP_HOST", "127.0.0.1")       # Funnel 이 localhost 로 넘겨줌 — 밖에서 직접은 못 들어옴
    print(f"토스봇 MCP http://{host}:{PORT}/<secret>/mcp → 대시보드 {DASH}", flush=True)
    ThreadingHTTPServer((host, PORT), H).serve_forever()
