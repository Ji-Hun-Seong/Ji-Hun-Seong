"""
주간 애크먼 TOP10 — 애크먼의 13년 매매 행태(13F 전 분기)로 뽑는 미국 주식 → 텔레그램 "Bilackman Portfolio"
  유니버스 : 애크먼이 2013년 이후 한 번이라도 의미 있게(비중 3%+) 보유한 상장 종목 전부 (현재 보유 여부·비중은 점수에 안 씀)
  애크먼 DNA: 처음 살 때 주가 위치(52주 고점 대비), 보유 기간, 보유 중 수익률
  점수(100): 매출성장 12 · 영업이익성장 12 · 잉여현금흐름 12 · 수익성 16 · 재무건전성 8 · 밸류에이션 10 ·
             애크먼 행태 일치 15 · AI·디지털 5 · 경쟁우위 10
  python 13f/ackman_weekly.py STATE.json [--send [--force]]
환경변수: SEC_UA, TG_TOKEN, TG_CHAT_ID
"""
import datetime as dt, html, json, math, os, statistics, sys, time
import xml.etree.ElementTree as ET
import requests

UA = {"User-Agent": os.environ.get("SEC_UA") or "research bot contact@example.com"}
CIKS = ("0001336528", "0002026053")          # Pershing Square Capital Mgmt(과거), Pershing Square Inc.(2025~)
KST = dt.timezone(dt.timedelta(hours=9))
METHOD = 2

# CUSIP → 현재 티커 (사명 변경·합병 반영)
CUSIP2T = {"009158106": "APD", "13645T100": "CP", "13646K108": "CP", "44267D107": "HHH", "44267T102": "HHH",
           "76131D103": "QSR", "121220107": "QSR", "72766Q105": "ESI", "98978V103": "ZTS", "91911K102": "BHC",
           "609207105": "MDLZ", "G6564A105": "NOMD", "169656105": "CMG", "053015103": "ADP", "654106103": "NKE",
           "913017109": "RTX", "548661107": "LOW", "43300A203": "HLT", "855244109": "SBUX", "084670702": "BRK-B",
           "00846U101": "A", "25754A201": "DPZ", "64110L106": "NFLX", "02079K107": "GOOGL", "02079K305": "GOOGL",
           "11271J107": "BN", "90353T100": "UBER", "023135106": "AMZN", "30303M102": "META", "594918104": "MSFT",
           "57636Q104": "MA", "78409V104": "SPGI", "92826C839": "V", "742718109": "PG", "42806J700": "HTZ",
           "812215200": "SEG", "812215101": "SEG"}
# 새 13F에 처음 보는 CUSIP이 나오면 이름으로 매핑
NAME2T = [("INTERCONTINENTAL EXCHANGE", "ICE"), ("ALCON", "ALC"), ("UNIVERSAL MUSIC", "UMGNF")]
SKIP = {"PERSHING SQUARE USA"}
MIN_W = 0.03                                 # 최대 비중 3% 미만(테스트성 소량)은 제외
FIN_LIKE = {"BN", "HHH", "BRK-B"}            # 지주·부동산·보험: 현금흐름 할인 대신 PER 방식만

KR = {"APD": "에어프로덕츠", "CP": "캐나디안퍼시픽", "HHH": "하워드휴즈", "QSR": "레스토랑브랜즈", "ESI": "엘리먼트솔루션즈",
      "ZTS": "조에티스", "BHC": "바슈헬스(구 밸리언트)", "MDLZ": "몬델리즈", "NOMD": "노마드푸드", "CMG": "치폴레",
      "ADP": "ADP", "NKE": "나이키", "RTX": "RTX(구 유나이티드테크)", "LOW": "로우스", "HLT": "힐튼", "SBUX": "스타벅스",
      "BRK-B": "버크셔해서웨이", "A": "애질런트", "DPZ": "도미노피자", "NFLX": "넷플릭스", "GOOGL": "알파벳",
      "BN": "브룩필드", "UBER": "우버", "AMZN": "아마존", "META": "메타", "MSFT": "마이크로소프트", "MA": "마스터카드",
      "SPGI": "S&P글로벌", "V": "비자", "PG": "P&G", "HTZ": "허츠", "SEG": "시포트", "ICE": "ICE", "ALC": "알콘"}

# 경쟁우위(애크먼 '20년 테스트', 0~10) · AI/디지털 수혜(0~5) — 정성 판단
MOAT = {"V": 10, "MA": 10, "SPGI": 10, "MSFT": 10, "GOOGL": 9, "AMZN": 9, "CP": 9, "META": 8, "NFLX": 8, "UBER": 8,
        "HLT": 8, "ADP": 9, "ZTS": 8, "CMG": 7, "LOW": 7, "QSR": 7, "DPZ": 7, "SBUX": 6, "BRK-B": 9, "BN": 7,
        "HHH": 6, "APD": 7, "MDLZ": 7, "NKE": 6, "RTX": 7, "A": 7, "PG": 8, "ESI": 5, "NOMD": 5, "BHC": 3,
        "ICE": 9, "ALC": 8, "HTZ": 2, "SEG": 3}
AI = {"MSFT": 5, "META": 5, "AMZN": 5, "GOOGL": 5, "UBER": 4, "NFLX": 3, "V": 3, "MA": 3, "SPGI": 3, "ADP": 3,
      "BN": 3, "ICE": 3, "APD": 2, "A": 2, "ESI": 2, "RTX": 2}

# thesis · 10년 전망 · 위험
THESIS = {
 "UBER": ("모빌리티·배달 1위 플랫폼, 이익·현금 본격화", "자율주행 차량을 모으는 수요 플랫폼으로 성장", "로보택시 업체의 직접 판매, 노동 규제"),
 "NFLX": ("스트리밍 승자, 가격 인상력 + 광고", "전 세계 TV 시청시간 점유율 확대", "콘텐츠 비용, 유튜브·숏폼 경쟁"),
 "META": ("광고 1위권 + AI로 광고 효율 상승", "AI 광고·메시징 수익화", "AI 설비투자 과다, 규제"),
 "MSFT": ("클라우드·오피스 구독 독점, AI 최대 수혜", "기업 AI 도입의 기본 인프라", "AI 투자 회수 지연"),
 "AMZN": ("AWS + 리테일 이익률 개선", "클라우드·광고 비중 확대", "설비투자 부담"),
 "GOOGL": ("검색·유튜브·클라우드", "AI 검색 전환 성공이 관건", "AI 챗봇의 검색 대체"),
 "BN": ("대체자산 운용·보험 복리 기계", "인프라·AI 데이터센터 자금 수요", "연결 부채, 금리"),
 "QSR": ("버거킹·팀홀튼·파파이스 로열티", "해외 매장 확대", "버거킹 미국 부진, 부채"),
 "HHH": ("애크먼이 키우는 지주사", "부동산 현금 + 인수로 복리", "현금흐름 변동, 이해상충"),
 "V": ("결제 통행료", "현금→카드 전환", "수수료 규제, 대체 결제"),
 "MA": ("결제 통행료(비자와 복점)", "해외 결제·부가서비스", "수수료 규제"),
 "SPGI": ("신용평가·지수 통행료", "채권 발행·패시브 투자 증가", "발행 경기, AI 데이터 경쟁"),
 "HLT": ("자산 안 들고 수수료 받는 호텔 프랜차이즈", "전 세계 객실 수 꾸준한 증가", "경기 침체 시 여행 수요"),
 "CMG": ("직영 패스트캐주얼 1위, 매장 확장", "북미 7천 매장 목표", "식품 안전, 인건비"),
 "LOW": ("미국 주택 리모델링 2강", "노후 주택 수리 수요", "주택 경기, 금리"),
 "CP": ("북미 3국 잇는 유일한 철도망", "멕시코 교역 증가", "물동량 경기, 노조"),
 "ADP": ("급여 처리 1위, 고객 이탈 적음", "중소기업 HR 아웃소싱", "고용 둔화, 금리 하락 시 이자수익 감소"),
 "ZTS": ("동물약품 1위", "반려동물 의료비 증가", "신약 경쟁"),
 "DPZ": ("배달 피자 1위, 프랜차이즈", "해외 매장 확대", "배달앱 경쟁"),
 "SBUX": ("커피 체인 1위 브랜드", "중국·해외 회복", "중국 경쟁, 매장 효율"),
 "BRK-B": ("버핏의 보험·자회사 복합기업", "현금으로 대형 인수", "승계 이후 문화"),
 "APD": ("산업용 가스 과점", "수소·반도체 가스", "대형 프로젝트 리스크"),
 "MDLZ": ("과자 글로벌 브랜드(오레오 등)", "신흥국 소비 증가", "원재료 가격"),
 "NKE": ("스포츠 브랜드 1위", "브랜드 회복", "경쟁 심화, 재고"),
 "RTX": ("항공 엔진·방산", "항공 수요·국방 예산", "엔진 결함 비용"),
 "A": ("분석 장비", "바이오·반도체 검사", "중국 수요"),
 "PG": ("생활용품 1위", "가격 결정력", "저성장"),
}

def get(url):
    for i in range(3):
        try:
            time.sleep(0.15)
            r = requests.get(url, headers=UA, timeout=40)
            r.raise_for_status()
            return r
        except Exception as e:
            err = e
            time.sleep(3)
    raise err


def num(x):
    try:
        x = float(x)
        return None if math.isnan(x) or math.isinf(x) else x
    except Exception:
        return None


def clamp(x, lo=0.0, hi=1.0):
    return lo if x is None else max(lo, min(hi, x))


# ── 13F 전 분기 이력 (상태 파일에 캐시, 새 분기만 받음) ──────────────
def all_filings():
    out = {}
    for cik in CIKS:
        d = get(f"https://data.sec.gov/submissions/CIK{cik}.json").json()
        blocks = [d["filings"]["recent"]] + [get(f"https://data.sec.gov/submissions/{f['name']}").json()
                                             for f in d["filings"].get("files", [])]
        for rec in blocks:
            for form, acc, rd, fd in zip(rec["form"], rec["accessionNumber"], rec["reportDate"], rec["filingDate"]):
                if form in ("13F-HR", "13F-HR/A"):
                    out.setdefault(rd, []).append((cik, acc, fd, form))
    return out


def holdings(cik, acc):
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}"
    items = get(f"{base}/index.json").json()["directory"]["item"]
    xml = next(i["name"] for i in items if i["name"].lower().endswith(".xml") and "primary_doc" not in i["name"].lower())
    root = ET.fromstring(get(f"{base}/{xml}").content)
    ns = {"n": root.tag.split("}")[0].strip("{")}
    out = {}
    for it in root.findall("n:infoTable", ns):
        if it.findtext("n:putCall", default="", namespaces=ns).strip():
            continue
        c = it.findtext("n:cusip", namespaces=ns).strip().upper()
        o = out.setdefault(c, {"name": it.findtext("n:nameOfIssuer", namespaces=ns).strip().upper(), "v": 0, "s": 0})
        o["v"] += int(float(it.findtext("n:value", namespaces=ns)))
        o["s"] += int(float(it.findtext("n:shrsOrPrnAmt/n:sshPrnamt", namespaces=ns)))
    vals = sorted(o["v"] / o["s"] for o in out.values() if o["s"])
    if vals and vals[len(vals) // 2] < 2:      # 천 달러 단위 신고 보정
        for o in out.values():
            o["v"] *= 1000
    return out


def update_history(hist):
    fl = all_filings()
    latest = sorted(fl)[-2:]                  # 최근 2분기는 정정 공시 반영 위해 매주 다시 받음
    for rd in sorted(fl):
        if rd in hist and rd not in latest:
            continue
        h, filed = {}, None
        for cik, acc, fd, form in sorted(fl[rd], key=lambda x: (x[3] != "13F-HR", x[2])):
            try:
                h.update(holdings(cik, acc))       # 원본 위에 정정분을 덮어씀 (정정이 1종목짜리여도 원본 유지)
                filed = filed or fd
            except Exception as e:
                if rd >= "2013":
                    print(f"::warning::13F {rd} {acc}: {str(e)[:100]}")
        if h:
            hist[rd] = {"filed": filed, "h": h}
    return hist


def ticker_of(c, name):
    if any(s in name for s in SKIP):
        return None
    return CUSIP2T.get(c) or next((t for k, t in NAME2T if k in name), None)


def episodes(hist):
    """종목별 보유 구간: [(첫 분기, 마지막 분기, 분기 수, 최대 비중)] — 1~2종목짜리 정정 분기는 건너뜀"""
    qs = [q for q in sorted(hist) if len(hist[q]["h"]) >= 3]
    held, maxw, unknown = {}, {}, set()
    for q in qs:
        tot = sum(o["v"] for o in hist[q]["h"].values()) or 1
        for c, o in hist[q]["h"].items():
            t = ticker_of(c, o["name"])
            if not t:
                if q >= qs[-2] and not any(s in o["name"] for s in SKIP):
                    unknown.add(o["name"])
                continue
            held.setdefault(t, set()).add(q)
            maxw[t] = max(maxw.get(t, 0), o["v"] / tot)
    for n in unknown:
        print(f"::warning::새 종목 티커 매핑 필요: {n}")
    eps = {}
    for t, s in held.items():
        if maxw[t] < MIN_W:
            continue
        idx = sorted(qs.index(q) for q in s)
        runs, start, prev = [], idx[0], idx[0]
        for i in idx[1:]:
            if i - prev > 2:                      # 2분기 넘게 비면 새 보유 구간
                runs.append((start, prev)); start = i
            prev = i
        runs.append((start, prev))
        eps[t] = [{"in": qs[a], "out": qs[b], "n": b - a + 1, "now": b == len(qs) - 1} for a, b in runs]
    return eps, qs[-1]


# ── 시세·재무 (yfinance) ───────────────────────────
def row(df, *names):
    if df is None or getattr(df, "empty", True):
        return []
    for n in names:
        if n in df.index:
            return [(c, num(v)) for c, v in zip(df.columns, df.loc[n].tolist()) if num(v) is not None]  # 최신→과거
    return []


def cagr(pairs, years=3):
    s = [v for _, v in pairs][: years + 1]
    if len(s) < 3 or s[0] <= 0 or s[-1] <= 0:
        return None
    return (s[0] / s[-1]) ** (1 / (len(s) - 1)) - 1


def fetch(t):
    import yfinance as yf
    tk = yf.Ticker(t)
    info = tk.info or {}
    fin = cf = None
    try:
        fin = tk.income_stmt
    except Exception:
        pass
    try:
        cf = tk.cashflow
    except Exception:
        pass
    fx = 1.0
    fc, tc = info.get("financialCurrency"), info.get("currency")
    if fc and tc and fc != tc:
        try:
            fx = float(yf.Ticker(f"{fc}{tc}=X").history(period="5d")["Close"].iloc[-1])
        except Exception as e:
            print(f"::warning::{t} 환율 {fc}{tc} 실패: {e}")
    px = tk.history(period="max", auto_adjust=True)["Close"]
    px = [(str(i.date()), float(v)) for i, v in px.items() if num(v)]
    return {"info": info, "rev": row(fin, "Total Revenue", "Operating Revenue"),
            "op": row(fin, "Operating Income", "EBIT"), "eps": row(fin, "Diluted EPS", "Basic EPS"),
            "ni": row(fin, "Net Income", "Net Income Common Stockholders"), "fcf": row(cf, "Free Cash Flow"), "px": px, "fx": fx}


def px_at(px, date):
    lo, hi = 0, len(px) - 1
    if not px or px[0][0] > date:
        return None
    while lo < hi:
        m = (lo + hi + 1) // 2
        if px[m][0] <= date:
            lo = m
        else:
            hi = m - 1
    return px[lo][1]


def dd52(px, date):
    """그 날짜 주가가 직전 1년 고점 대비 몇 % 아래인지"""
    d0 = (dt.date.fromisoformat(date) - dt.timedelta(days=365)).isoformat()
    win = [v for d, v in px if d0 <= d <= date]
    p = px_at(px, date)
    return p / max(win) - 1 if win and p else None


def q_start(q):
    d = dt.date.fromisoformat(q)
    return (d - dt.timedelta(days=91)).isoformat()


# ── 애크먼 DNA ────────────────────────────────────
def dna(eps, data, last_q):
    entries, rets, holds = [], [], []
    per_t = {}
    for t, runs in eps.items():
        px = (data.get(t) or {}).get("px")
        if not px:
            continue
        rs = []
        for r in runs:
            d_in = q_start(r["in"])                       # 분기 초 = 애크먼이 사기로 결정한 시점의 가격
            d_out = data[t]["px"][-1][0] if r["now"] else r["out"]
            p0, p1 = px_at(px, d_in), px_at(px, d_out)
            dd = dd52(px, d_in)
            yrs = max(0.25, (dt.date.fromisoformat(d_out) - dt.date.fromisoformat(d_in)).days / 365)
            ret = p1 / p0 - 1 if p0 and p1 else None
            ann = (1 + ret) ** (1 / yrs) - 1 if ret is not None and ret > -1 else None
            r.update({"dd": dd, "ret": ret, "ann": ann})
            if r["in"] > "2013-06-30" and dd is not None:     # 2013-06 이전부터 들고 있던 건 진입 시점 모름
                entries.append(dd)
            if ann is not None:
                rets.append(ann)
            holds.append(r["n"])
            rs.append(r)
        per_t[t] = rs
    entries.sort()
    q = lambda p: entries[min(len(entries) - 1, int(p * len(entries)))] if entries else None
    return {"dd_med": statistics.median(entries) if entries else -0.2, "dd_lo": q(0.25), "dd_hi": q(0.75),
            "n": len(entries), "hold_med": statistics.median(holds) if holds else 6,
            "win": sum(1 for x in rets if x > 0) / len(rets) if rets else None, "per_t": per_t}


# ── 평가 ──────────────────────────────────────────
def pe_hist(d):
    """최근 4~5개 회계연도 말 주가 ÷ 그해 EPS 의 중앙값 (과거 PER)"""
    vals = []
    for c, e in d["eps"]:
        if e and e > 0:
            p = px_at(d["px"], str(c.date()) if hasattr(c, "date") else str(c)[:10])
            if p:
                vals.append(p / (e * d.get("fx", 1.0)))
    vals = [v for v in vals if 3 < v < 150]
    return statistics.median(vals) if len(vals) >= 2 else None


def evaluate(t, d, D):
    i = d["info"]
    price = d["px"][-1][1] if d["px"] else num(i.get("currentPrice"))
    rg, og = cagr(d["rev"]), cagr(d["op"])
    mc = num(i.get("marketCap"))
    fcf = d["fcf"][0][1] if d["fcf"] else num(i.get("freeCashflow"))
    ni = d["ni"][0][1] if d["ni"] else num(i.get("netIncomeToCommon"))
    fl = [v for _, v in d["fcf"][:4]]
    pos_years = sum(1 for v in fl if v > 0) / len(fl) if fl else (1.0 if (fcf or 0) > 0 else 0.0)
    opm, roe = num(i.get("operatingMargins")), num(i.get("returnOnEquity"))
    ebitda = num(i.get("ebitda"))
    nd = (num(i.get("totalDebt")) or 0) - (num(i.get("totalCash")) or 0)
    lev = nd / ebitda if ebitda and ebitda > 0 else (99 if nd > 0 else -1)
    fx = d.get("fx", 1.0)                                  # 재무제표 통화 → 거래 통화 (예: CP는 CAD)
    fcf = fcf * fx if fcf is not None else None
    ni = ni * fx if ni is not None else None
    fy = fcf / mc if fcf is not None and mc else None
    fpe = num(i.get("forwardPE"))
    if fpe and fpe > 0 and price:
        feps = price / fpe
    else:
        feps = num(i.get("forwardEps"))
        feps = feps * fx if feps else None
        fpe = price / feps if feps and feps > 0 and price else None
    ph = pe_hist(d)

    # 적정주가: ① PER 방식 = 선행EPS × 과거 PER  ② 현금흐름 할인(10년, 할인율 9%)
    fv_parts = {}
    if feps and feps > 0:
        tpe = clamp(ph, 10, 35) if ph else 18
        fv_parts["per"] = (feps, tpe, feps * tpe)
    if t not in FIN_LIKE:
        sh = num(i.get("sharesOutstanding")) or (mc / price if mc and price else None)
        cash, norm = fcf, False
        if ni and ni > 0 and (cash is None or cash < 0.6 * ni):
            cash, norm = 0.8 * ni, True                    # 설비투자로 FCF가 눌린 경우 순이익 기준
        if cash and cash > 0 and sh:
            g1, r, v, c = clamp(rg, 0, 0.15), 0.09, 0.0, cash / sh
            for y in range(1, 11):
                c *= 1 + (g1 if y <= 5 else g1 / 2)
                v += c / (1 + r) ** y
            v += c * 1.03 / (r - 0.03) / (1 + r) ** 10
            fv_parts["dcf"] = (v, norm, g1)
    vals = [fv_parts["per"][2]] if "per" in fv_parts else []
    if "dcf" in fv_parts:
        if vals and not (1 / 2.5 < fv_parts["dcf"][0] / vals[0] < 2.5):
            fv_parts["dcf_drop"] = fv_parts.pop("dcf")       # 두 방법이 2.5배 넘게 차이 나면 이익 기반만 사용
        else:
            vals.append(fv_parts["dcf"][0])
    fv = statistics.mean(vals) if vals else None

    # 밸류: 지금 PER이 자기 과거 PER보다 얼마나 낮은지 + FCF수익률
    if fpe and ph:
        v1 = clamp((ph / fpe - 0.7) / 0.6) * 6
    elif fpe:
        v1 = clamp((25 - fpe) / 15) * 6
    else:
        v1 = 2
    val = v1 + clamp((fy or 0) / 0.06) * 4

    # 애크먼 행태 일치: ① 지금 주가 위치가 그가 처음 살 때 위치와 비슷한가 ② 과거에 오래·좋게 들고 갔나
    cur_dd = dd52(d["px"], d["px"][-1][0]) if d["px"] else None
    m = D["dd_med"]
    timing = clamp(1 - abs((cur_dd if cur_dd is not None else 0) - m) / 0.25) * 8
    runs = D["per_t"].get(t, [])
    nq = sum(r["n"] for r in runs)
    anns = [r["ann"] for r in runs if r["ann"] is not None]
    best = max(anns) if anns else None
    track = clamp(nq / 20) * 3.5 + clamp(((best if best is not None else 0) + 0.05) / 0.25) * 3.5

    pts = {"매출성장": clamp(rg / 0.15) * 12 if rg is not None else 4.8,
           "영업이익성장": clamp(og / 0.20) * 12 if og is not None else 4.8,
           "잉여현금흐름": clamp((fy or 0) / 0.06) * 6 + pos_years * 6,
           "수익성": clamp((opm or 0) / 0.35) * 8 + clamp((roe or 0) / 0.30) * 8,
           "재무건전성": clamp((4 - lev) / 4) * 8,
           "밸류에이션": val,
           "애크먼행태": timing + track,
           "AI·디지털": AI.get(t, 1),
           "경쟁우위": MOAT.get(t, 5)}
    return {"t": t, "total": sum(pts.values()), "pts": pts, "price": price, "fv": fv, "fvp": fv_parts,
            "buy": fv * 0.8 if fv else None, "rg": rg, "og": og, "fy": fy, "opm": opm, "lev": lev, "fpe": fpe,
            "ph": ph, "dd": cur_dd, "runs": runs, "timing": timing}


# ── 메시지 ─────────────────────────────────────────
def pct(x):
    return "-" if x is None else f"{x * 100:+.0f}%"


def money(x):
    return "-" if x is None else (f"${x:,.0f}" if x >= 100 else f"${x:,.2f}")


def status(s):
    if s["fv"] is None:
        return "⚪", "적정가 계산 불가"
    if s["price"] <= s["buy"]:
        return "🟢", "매수 구간"
    if s["price"] <= s["fv"]:
        return "🟡", "적정가 이하 · 분할 매수"
    return "🔴", "적정가 초과 · 대기"


def qlabel(q):
    return f"{q[2:4]}.{(int(q[5:7]) + 2) // 3}Q"


def history_line(runs):
    if not runs:
        return "애크먼 보유 이력 없음"
    out = []
    for r in runs:
        span = f"{qlabel(r['in'])}~{'보유 중' if r['now'] else qlabel(r['out'])}"
        out.append(f"{span} {r['n']}분기, 주가 {pct(r['ret'])}")
    return "애크먼: " + " / ".join(out)


def build(res, D, state, week, asof, last_q):
    prev_rank = state.get("ranks", {}) if state.get("method") == METHOD else {}
    base = state.get("baseline", {}) if state.get("method") == METHOD else {}
    top = res[:10]
    m1 = [f"🧬 <b>애크먼 매매 행태 (13F {D['first_q'][:4]}~{last_q[:4]}, {len(D['per_t'])}종목)</b>",
          f"▪ 처음 살 때 주가: 52주 고점 대비 중앙값 <b>{pct(D['dd_med'])}</b> (절반은 {pct(D['dd_lo'])} ~ {pct(D['dd_hi'])} 사이, {D['n']}건)",
          f"▪ 보유 기간 중앙값 {D['hold_med']:.0f}분기 · 보유 구간 중 주가가 오른 비율 {('-' if D['win'] is None else f'{D['win'] * 100:.0f}%')}",
          "▪ 오래 들고 간 종목: " + ", ".join(f"{KR.get(t, t)} {sum(r['n'] for r in rs)}분기"
                                       for t, rs in sorted(D["per_t"].items(), key=lambda x: -sum(r['n'] for r in x[1]))[:6]),
          "▪ 좋아하는 사업: 단순·예측 가능, 잉여현금 많음, 진입장벽(브랜드·네트워크·통행료), 부채 적당",
          "",
          "→ 그래서 이 봇은 '애크먼이 지금 갖고 있나'가 아니라, 그가 과거에 산 종목들 중 <b>지금 그가 사던 때와 비슷한 상태</b>인 종목을 찾습니다."]
    m2 = [f"📅 <b>주간 애크먼 TOP10</b> · {week}", f"미국 {asof} 종가 기준", ""]
    for n, s in enumerate(top, 1):
        pr = prev_rank.get(s["t"])
        mv = "" if not prev_rank else (" 🆕" if pr is None else ("" if pr == n else (f" ▲{pr - n}" if pr > n else f" ▼{n - pr}")))
        e, _ = status(s)
        per = f"PER {s['fpe']:.0f}배" if s["fpe"] else "PER -"
        per += f"(과거 {s['ph']:.0f}배)" if s["ph"] else ""
        m2.append(f"{n}. {e} <b>{KR.get(s['t'], s['t'])}</b> ({s['t']}) {s['total']:.0f}점{mv}")
        m2.append(f"    {money(s['price'])} · {per} · 적정 {money(s['fv'])} · 매수 ≤{money(s['buy'])}")
    out_ = [KR.get(t, t) for t in prev_rank if t not in [s["t"] for s in top]]
    if out_:
        m2 += ["", "↘️ 이번 주 TOP10 이탈: " + ", ".join(out_)]
    m2 += ["", "🟢 적정가보다 20%+ 쌈 · 🟡 적정가 이하 · 🔴 적정가 초과 · ⚪ 계산 불가",
           "PER = 주가 ÷ 내년 예상 주당순이익(배). 과거 = 최근 4~5년 결산 시점 PER 중앙값",
           "점수(100): 매출성장 12 · 영업이익성장 12 · 잉여현금흐름 12 · 수익성 16 · 재무 8 · 밸류 10 · 애크먼 행태 일치 15 · AI·디지털 5 · 경쟁우위 10"]
    blocks = []
    for n, s in enumerate(top, 1):
        t = s["t"]
        e, word = status(s)
        b = [f"<b>{n}. {KR.get(t, t)} ({t}) — {s['total']:.0f}점</b>", f"{e} {word} · 현재 {money(s['price'])}"]
        fp = s["fvp"]
        calc = []
        if "per" in fp:
            calc.append(f"내년 EPS ${fp['per'][0]:.2f} × PER {fp['per'][1]:.0f}배 = {money(fp['per'][2])}")
        if "dcf" in fp:
            calc.append(f"현금흐름 할인 {money(fp['dcf'][0])}" + (" (순이익 기준)" if fp["dcf"][1] else ""))
        if "dcf_drop" in fp:
            calc.append(f"현금흐름 할인 {money(fp['dcf_drop'][0])}은 편차가 커서 제외")
        if calc:
            b.append(f"▪ 적정가 {money(s['fv'])} = 평균[{' / '.join(calc)}] · 매수가 {money(s['buy'])}(−20%)")
        b.append(f"▪ 3년 성장: 매출 {pct(s['rg'])}/년 · 영업이익 {pct(s['og'])}/년 · 영업이익률 "
                 f"{'-' if s['opm'] is None else f'{s['opm'] * 100:.0f}%'} · FCF수익률 {'-' if s['fy'] is None else f'{s['fy'] * 100:.1f}%'}")
        b.append(f"▪ 주가 위치: 52주 고점 대비 {pct(s['dd'])} (애크먼 매수 시 중앙값 {pct(D['dd_med'])})")
        b.append("▪ " + history_line(s["runs"]))
        th = THESIS.get(t)
        if th:
            b += [f"▪ 투자 포인트: {th[0]}", f"▪ 10년 전망: {th[1]} · 위험: {th[2]}"]
        bl = base.get(t)
        warn = []
        if s["rg"] is not None and s["rg"] < 0:
            warn.append("매출 역성장")
        if bl and s["opm"] is not None and bl.get("opm") is not None and s["opm"] < bl["opm"] - 0.05:
            warn.append(f"영업이익률 {bl['opm'] * 100:.0f}%→{s['opm'] * 100:.0f}%")
        if bl and bl.get("price") and s["price"] < bl["price"] * 0.75:
            warn.append(f"편입 후 {pct(s['price'] / bl['price'] - 1)}")
        b.append("✅ 투자 포인트 유효" if not warn else "⚠️ 점검 필요: " + ", ".join(warn))
        b.append("▪ 점수: " + " · ".join(f"{k} {v:.0f}" for k, v in s["pts"].items()))
        blocks.append("\n".join(b))
    tail = ["📌 <b>11위 이하</b>", ", ".join(f"{KR.get(s['t'], s['t'])} {s['total']:.0f}" for s in res[10:]), "",
            "※ 적정가는 단순 모델 추정치. 매수가 = 적정가 × 0.8(안전마진 20%). 재무 수치 yfinance(연간 결산) 기준.",
            "※ 애크먼 수익률은 보유 분기 시작~끝 주가 변화로 추정(실제 매매가와 다름). 투자 자문 아님."]
    msgs, cur = ["\n".join(m1), "\n".join(m2)], ""
    for b in blocks:
        if len(cur) + len(b) > 3500:
            msgs.append(cur.strip()); cur = ""
        cur += b + "\n\n"
    if cur.strip():
        msgs.append(cur.strip())
    msgs.append("\n".join(tail))
    return msgs


def send(text):
    tok, chat = os.environ["TG_TOKEN"], os.environ["TG_CHAT_ID"]
    for _ in range(2):
        r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                          json={"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}, timeout=30)
        j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        new = (j.get("parameters") or {}).get("migrate_to_chat_id")
        if not r.ok and new:
            print(f"::warning::그룹이 슈퍼그룹으로 바뀜 {chat} → {new} (워크플로 TG_CHAT_ID 갱신 필요)")
            os.environ["TG_CHAT_ID"] = chat = str(new)
            continue
        if not r.ok:
            raise RuntimeError(f"텔레그램 {r.status_code}: {r.text[:200]}")
        return
    raise RuntimeError("전송 실패")


def main():
    state_path = sys.argv[1]
    do_send, force = "--send" in sys.argv, "--force" in sys.argv
    state = json.load(open(state_path)) if os.path.exists(state_path) else {}
    now = dt.datetime.now(KST)
    y, w, _ = now.isocalendar()
    week = f"{y}-W{w:02d}"
    if do_send and state.get("sent_week") == week and state.get("method") == METHOD and not force:
        print(f"::notice::{week} 이미 전송함 → 건너뜀")
        return

    hist = update_history(state.get("hist", {}))
    eps, last_q = episodes(hist)
    print(f"::notice::13F {len(hist)}분기, 유니버스 {len(eps)}종목: {sorted(eps)}")
    data, fail = {}, []
    for t in eps:
        try:
            data[t] = fetch(t)
            if not data[t]["px"]:
                raise ValueError("가격 없음")
        except Exception as e:
            fail.append(t); data.pop(t, None)
            print(f"::warning::{t} 데이터 실패: {str(e)[:150]}")
        time.sleep(0.4)
    if len(data) < max(8, len(eps) * 2 // 3):
        print(f"::error::데이터 부족 ({len(data)}/{len(eps)}) → 전송 안 함"); sys.exit(1)
    D = dna(eps, data, last_q)
    D["first_q"] = min(r["in"] for rs in D["per_t"].values() for r in rs)
    res = []
    for t in data:
        try:
            res.append(evaluate(t, data[t], D))
        except Exception as e:
            print(f"::warning::{t} 평가 실패: {type(e).__name__} {str(e)[:150]}")
    res.sort(key=lambda s: -s["total"])
    asof = max(d["px"][-1][0] for d in data.values())
    msgs = build(res, D, state, week, asof, last_q)
    for i, m in enumerate(msgs, 1):
        assert len(m) < 4096, (i, len(m))
        if do_send:
            send(m); print(f"::notice::전송 {i}/{len(msgs)}"); time.sleep(1)
        else:
            print("::notice::" + m.replace("%", "%25").replace("\n", "%0A"))
    state["hist"] = hist                      # 13F 캐시는 미리보기여도 저장
    if do_send:
        base = state.get("baseline", {}) if state.get("method") == METHOD else {}
        for s in res[:10]:
            base.setdefault(s["t"], {"date": asof, "price": s["price"], "opm": s["opm"]})
        state.update({"ranks": {s["t"]: n for n, s in enumerate(res[:10], 1)}, "baseline": base,
                      "sent_week": week, "method": METHOD})
    state["last_run"] = now.isoformat(timespec="minutes")
    json.dump(state, open(state_path, "w"), ensure_ascii=False)


if __name__ == "__main__":
    main()
