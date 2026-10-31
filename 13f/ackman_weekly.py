"""
주간 애크먼 TOP10 — 13F 자동 유니버스 + 100점 평가 + 적정주가·매수가격 + 투자 thesis 점검 → 텔레그램 "Bilackman Portfolio"
  python 13f/ackman_weekly.py STATE.json                 # 미리보기 (Actions notice)
  python 13f/ackman_weekly.py STATE.json --send          # 전송 (이번 주 이미 보냈으면 건너뜀)
  python 13f/ackman_weekly.py STATE.json --send --force  # 이번 주 재전송
  python 13f/ackman_weekly.py STATE.json --fixture market.json   # 오프라인 점검용 (재무제표 없이)
환경변수: SEC_UA, TG_TOKEN, TG_CHAT_ID
"""
import datetime as dt, html, json, math, os, statistics, sys, time
import xml.etree.ElementTree as ET
import requests

UA = {"User-Agent": os.environ.get("SEC_UA") or "research bot contact@example.com"}
CIKS = ("0002026053", "0001336528")          # Pershing Square Inc.(현재), Pershing Square Capital Mgmt(과거)
KST = dt.timezone(dt.timedelta(hours=9))

# 13F 종목명 → 티커 (대문자 부분일치)
NAME2T = [("UBER", "UBER"), ("BROOKFIELD CORP", "BN"), ("MICROSOFT", "MSFT"), ("AMAZON", "AMZN"),
          ("HOWARD HUGHES", "HHH"), ("RESTAURANT BRANDS", "QSR"), ("META PLATFORMS", "META"), ("VISA", "V"),
          ("MASTERCARD", "MA"), ("S&P GLOBAL", "SPGI"), ("NETFLIX", "NFLX"), ("ALPHABET", "GOOGL"),
          ("CHIPOTLE", "CMG"), ("HILTON", "HLT"), ("LOWES", "LOW"), ("LOWE'S", "LOW"),
          ("INTERCONTINENTAL EXCHANGE", "ICE"), ("ALCON", "ALC"), ("SEAPORT ENTMT", "SEG"), ("SEAPORT ENTERTAINMENT", "SEG"),
          ("HERTZ", "HTZ"), ("CANADIAN PAC", "CP"), ("NIKE", "NKE"), ("UNIVERSAL MUSIC", "UMGNF")]
SKIP_NAMES = ("PERSHING SQUARE USA",)       # 애크먼 자기 펀드 → 평가 제외
WATCH = ["ICE", "ALC"]                      # 13F 이후 매수 보도(미확인) → 관찰 후보로 같이 평가
FIN_LIKE = {"BN", "HHH", "SEG"}             # 지주·부동산: FCF 기반 적정가가 의미 없음

# 경쟁우위(애크먼 '20년 테스트', 0~10)·AI/디지털 수혜(0~5) — 정성 판단
MOAT = {"V": 10, "MA": 10, "SPGI": 10, "ICE": 9, "MSFT": 10, "GOOGL": 9, "META": 8, "AMZN": 9, "NFLX": 8,
        "UBER": 8, "QSR": 7, "CMG": 7, "HLT": 8, "LOW": 7, "ALC": 8, "BN": 7, "HHH": 6, "CP": 9, "SEG": 3, "HTZ": 2}
AI = {"MSFT": 5, "META": 5, "AMZN": 5, "GOOGL": 5, "UBER": 4, "NFLX": 3, "V": 3, "MA": 3, "SPGI": 3, "ICE": 3,
      "BN": 3, "QSR": 1, "HHH": 1, "ALC": 1, "CMG": 1, "HLT": 1, "LOW": 1, "CP": 1, "SEG": 0, "HTZ": 1}

# 투자 thesis · 10년 전망 · 위험 · thesis가 깨지는 신호
THESIS = {
 "UBER": ("모빌리티·배달 1위 플랫폼, 이익·FCF가 이제 막 본격화",
          "자율주행 차량을 모으는 '수요 플랫폼'이 되면 장기 성장 지속",
          "로보택시 업체가 직접 고객을 가져갈 위험, 기사 노동 규제"),
 "NFLX": ("스트리밍 전쟁 승자, 구독료 인상력 + 광고 요금제",
          "전 세계 TV 시간 점유율 확대, '고성장 유틸리티'형 현금 창출",
          "콘텐츠 비용 급증, 유튜브·숏폼과 시간 경쟁"),
 "META": ("광고 1위권 + AI로 광고 효율 상승, 애크먼 '믿기 힘든 저평가'",
          "AI 광고·메시징 수익화로 10년 성장, 30억명+ 사용자 기반",
          "AI 설비투자 과다, 규제·소송"),
 "MSFT": ("클라우드(Azure)·오피스 구독 독점력, AI 최대 수혜",
          "기업 AI 도입의 기본 인프라로 10년 복리 성장",
          "AI 투자 회수 지연, 이미 높은 밸류"),
 "AMZN": ("AWS + 리테일 이익률 개선",
          "클라우드·광고 고마진 사업 비중 확대로 이익 성장",
          "설비투자 부담, 애크먼이 2분기 25% 축소"),
 "BN": ("대체자산 운용(BAM)·보험 복리 기계, 순자산 대비 할인",
        "인프라·재생에너지·AI 데이터센터 자금 수요로 운용자산 확대",
        "연결 부채 큼, 금리 상승기 자산가치 하락"),
 "QSR": ("버거킹·팀홀튼·파파이스 프랜차이즈 로열티, 12년 보유 핵심",
         "해외 매장 확대 + 로열티 구조로 꾸준한 현금",
         "버거킹 미국 부진, 높은 부채"),
 "HHH": ("애크먼이 '현대판 버크셔'로 키우는 지주사",
         "부동산 현금 + 인수합병으로 복리 성장 — 사실상 애크먼에 대한 베팅",
         "현금흐름 들쭉날쭉, 지배주주 이해상충"),
 "V": ("결제 '통행료' — 거래액만큼 수수료",
       "현금→카드 전환 지속, 10년 이상 두 자릿수 이익 성장 기대",
       "수수료 규제, 스테이블코인·실시간 결제 대체"),
 "MA": ("결제 '통행료' — Visa와 복점",
        "해외 결제·부가서비스 성장",
        "수수료 규제, 대체 결제망"),
 "SPGI": ("신용평가·S&P 지수 '통행료'",
          "채권 발행·패시브 투자 증가에 따라 자동 성장",
          "발행 경기 둔화, AI가 데이터 사업 잠식"),
 "ICE": ("거래소·모기지 데이터 '통행료'",
         "데이터·청산 수요 꾸준", "모기지 사업 부진"),
 "ALC": ("안과 수술장비·렌즈 세계 1위",
         "고령화로 백내장 수술 증가", "미국 의료 가격 규제"),
 "GOOGL": ("검색·유튜브·클라우드", "AI 검색 전환 성공 여부가 관건", "AI 챗봇이 검색 대체 — 애크먼 전량 매도"),
}

MAX_W = 0.12        # 13F 비중 12% → 보유 점수 만점


def get(url):
    for i in range(3):
        try:
            time.sleep(0.2)
            r = requests.get(url, headers=UA, timeout=40)
            r.raise_for_status()
            return r
        except Exception as e:
            err = e
            time.sleep(3)
    raise err


# ── 13F ─────────────────────────────────────────────
def filings_by_quarter():
    out = {}
    for cik in CIKS:
        rec = get(f"https://data.sec.gov/submissions/CIK{cik}.json").json()["filings"]["recent"]
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
        name = it.findtext("n:nameOfIssuer", namespaces=ns).strip().upper()
        o = out.setdefault(name, {"value": 0, "shares": 0})
        o["value"] += int(float(it.findtext("n:value", namespaces=ns)))
        o["shares"] += int(float(it.findtext("n:shrsOrPrnAmt/n:sshPrnamt", namespaces=ns)))
    vals = sorted(o["value"] / o["shares"] for o in out.values() if o["shares"])
    if vals and vals[len(vals) // 2] < 2:
        for o in out.values():
            o["value"] *= 1000
    return out


def quarter(fl):
    """원본 13F-HR에 정정(13F-HR/A)을 덮어씀. 정정이 1~2종목짜리여도 원본이 사라지지 않게."""
    h, filed = {}, None
    for cik, acc, fd, form in sorted(fl, key=lambda x: (x[3] != "13F-HR", x[2])):
        try:
            h.update(holdings(cik, acc))
            filed = filed or fd
        except Exception as e:
            print(f"::warning::13F {acc}: {str(e)[:120]}")
    return h, filed


def to_ticker(name):
    if any(s in name for s in SKIP_NAMES):
        return None
    for key, t in NAME2T:
        if key in name:
            return t
    print(f"::warning::티커 매핑 없음 → 제외: {name}")
    return None


def ackman_13f():
    fq = filings_by_quarter()
    qs = sorted(fq, reverse=True)
    cur, filed = quarter(fq[qs[0]])
    prev, _ = quarter(fq[qs[1]])
    tot = sum(v["value"] for v in cur.values()) or 1
    pos = {}
    for name, v in cur.items():
        t = to_ticker(name)
        if not t:
            continue
        p = next((pv for pn, pv in prev.items() if to_ticker_quiet(pn) == t), None)
        chg = None if not p else (v["shares"] / p["shares"] - 1 if p["shares"] else 0)
        pos[t] = {"w": v["value"] / tot, "chg": chg, "new": p is None, "name": name.title()}
    exits = sorted({to_ticker_quiet(n) for n in prev} - set(pos) - {None})
    return {"date": qs[0], "filed": filed, "pos": pos, "exits": exits, "total": tot}


def to_ticker_quiet(name):
    if any(s in name for s in SKIP_NAMES):
        return None
    return next((t for key, t in NAME2T if key in name), None)


# ── 시세·재무 ───────────────────────────────────────
def num(x):
    try:
        x = float(x)
        return None if math.isnan(x) or math.isinf(x) else x
    except Exception:
        return None


def row(df, *names):
    if df is None or getattr(df, "empty", True):
        return []
    for n in names:
        if n in df.index:
            return [v for v in (num(x) for x in df.loc[n].tolist()) if v is not None]   # 최신 → 과거
    return []


def cagr(series):
    s = series[:4]
    if len(s) < 2 or s[-1] <= 0 or s[0] <= 0:
        return None
    return (s[0] / s[-1]) ** (1 / (len(s) - 1)) - 1


def fetch(t, fixture=None):
    if fixture is not None:
        info = (fixture.get(t) or {}).get("info") or {}
        px = (fixture.get(t) or {}).get("px") or []
        return {"info": info, "rev": [], "ni": [], "fcf": [], "price": px[-1][1] if px else info.get("currentPrice"),
                "high": max((p[1] for p in px[-252:]), default=None)}
    import yfinance as yf
    tk = yf.Ticker(t)
    info = tk.info or {}
    try:
        fin = tk.income_stmt
    except Exception:
        fin = None
    try:
        cf = tk.cashflow
    except Exception:
        cf = None
    hist = tk.history(period="1y")["Close"]
    return {"info": info, "rev": row(fin, "Total Revenue", "Operating Revenue"),
            "ni": row(fin, "Net Income", "Net Income Common Stockholders"),
            "fcf": row(cf, "Free Cash Flow"),
            "price": num(hist.iloc[-1]) if len(hist) else num(info.get("currentPrice")),
            "high": num(hist.max()) if len(hist) else num(info.get("fiftyTwoWeekHigh"))}


def clamp(x, lo=0.0, hi=1.0):
    return lo if x is None else max(lo, min(hi, x))


def fair_value(t, d, g):
    """적정주가 = PER법 · 10년 현금흐름 할인(DCF) · FCF수익률법의 중앙값. 매수가격 = 적정가 × 0.8 (안전마진 20%).
    AI 설비투자 등으로 FCF가 순이익의 60%에 못 미치면 '정상화 현금'(순이익 × 0.8)을 씀."""
    i, price = d["info"], d["price"]
    if t in FIN_LIKE or not price:
        return None, [], False
    sh = num(i.get("sharesOutstanding")) or (num(i.get("marketCap")) / price if num(i.get("marketCap")) else None)
    eps, fcf = num(i.get("forwardEps")), num(i.get("freeCashflow"))
    ni = num(i.get("netIncomeToCommon")) or ((num(i.get("trailingEps")) or 0) * sh if sh else None)
    gg = clamp(g, 0, 0.20)
    out, norm = [], False
    if eps and eps > 0:
        out.append(("PER", eps * (12 + 0.65 * gg * 100)))          # 성장 0% → PER 12, 20% → PER 25
    cash = fcf
    if ni and ni > 0 and (cash is None or cash < 0.6 * ni):
        cash, norm = 0.8 * ni, True
    if cash and cash > 0 and sh:
        cps = cash / sh
        g1, r, v, c = min(gg, 0.15), 0.09, 0.0, cps
        for y in range(1, 11):
            c *= 1 + (g1 if y <= 5 else g1 / 2)
            v += c / (1 + r) ** y
        v += c * 1.03 / (r - 0.03) / (1 + r) ** 10
        out.append(("DCF", v))
        opm = num(i.get("operatingMargins")) or 0
        out.append(("FCF수익률", cps / (0.045 if opm > 0.2 else 0.06)))
    if not out:
        return None, [], False
    return statistics.median(v for _, v in out), out, norm


def score(t, d, own):
    i, price = d["info"], d["price"]
    rg_hist, ni_hist = cagr(d["rev"]), cagr(d["ni"])
    rg_q, eg_q = num(i.get("revenueGrowth")), num(i.get("earningsGrowth"))
    rg = statistics.mean([x for x in (rg_hist, rg_q) if x is not None]) if (rg_hist is not None or rg_q is not None) else None
    ng = statistics.mean([x for x in (ni_hist, eg_q) if x is not None]) if (ni_hist is not None or eg_q is not None) else None
    mc, fcf = num(i.get("marketCap")), num(i.get("freeCashflow"))
    fy = fcf / mc if fcf is not None and mc else None
    pos_years = sum(1 for x in d["fcf"][:4] if x > 0) / len(d["fcf"][:4]) if d["fcf"] else (1.0 if (fcf or 0) > 0 else 0.0)
    opm, roe = num(i.get("operatingMargins")), num(i.get("returnOnEquity"))
    ebitda = num(i.get("ebitda"))
    nd = (num(i.get("totalDebt")) or 0) - (num(i.get("totalCash")) or 0)
    lev = nd / ebitda if ebitda and ebitda > 0 else (99 if nd > 0 else -1)
    fv, methods, norm = fair_value(t, d, rg if rg is not None else 0.05)
    fpe = num(i.get("forwardPE"))
    if fv and price:
        up = fv / price - 1
        val = clamp((up + 0.2) / 0.5) * 10                 # 적정가 대비 −20% 비쌈 → 0점, +30% 쌈 → 10점
    else:
        up = None
        val = clamp((25 - fpe) / 15) * 10 if fpe and fpe > 0 else 5
    p = own.get(t)
    if p:
        hold = clamp(p["w"] / MAX_W) * 10
        trade = 5 if p["new"] or (p["chg"] or 0) > 0.05 else (1 if (p["chg"] or 0) < -0.2 else 3)
    else:
        hold, trade = (3, 2) if t in WATCH else (0, 0)
    pts = {"매출성장": clamp(rg / 0.15 if rg is not None else None) * 12,
           "순이익성장": clamp(ng / 0.20 if ng is not None else None) * 12,
           "잉여현금흐름": clamp(fy / 0.06 if fy is not None else None) * 6 + pos_years * 6,
           "수익성": clamp((opm or 0) / 0.35) * 8 + clamp((roe or 0) / 0.30) * 8,
           "재무건전성": clamp((4 - lev) / 4) * 8,
           "밸류에이션": val,
           "PS보유": hold,
           "AI·디지털": AI.get(t, 1),
           "경쟁우위": MOAT.get(t, 5),
           "애크먼매매": trade}
    return {"t": t, "total": sum(pts.values()), "pts": pts, "price": price, "fv": fv, "methods": methods, "up": up,
            "buy": fv * 0.8 if fv else None, "norm": norm, "rg": rg, "ng": ng, "fy": fy, "opm": opm, "roe": roe, "lev": lev, "fpe": fpe,
            "high": d["high"], "target": num(i.get("targetMeanPrice")), "name": i.get("shortName") or t}


# ── 메시지 ──────────────────────────────────────────
def pct(x, d=0):
    return "-" if x is None else f"{x * 100:+.{d}f}%"


def money(x):
    return "-" if x is None else (f"${x:,.0f}" if x >= 100 else f"${x:,.2f}")


def status(s):
    if s["fv"] is None:
        return "⚪ 적정가 산출 제외(지주·부동산)"
    if s["price"] <= s["buy"]:
        return "🟢 매수 구간"
    if s["price"] <= s["fv"]:
        return "🟡 적정가 이하 · 분할 매수"
    return "🔴 적정가 초과 · 대기"


def thesis_check(s, own, base):
    bad = []
    p = own.get(s["t"])
    if p and (p["chg"] or 0) <= -0.25:
        bad.append(f"애크먼이 {abs(p['chg']) * 100:.0f}% 축소")
    if s["rg"] is not None and s["rg"] < 0:
        bad.append("매출 역성장")
    b = base.get(s["t"])
    if b:
        if s["opm"] is not None and b.get("opm") is not None and s["opm"] < b["opm"] - 0.05:
            bad.append(f"영업이익률 {b['opm'] * 100:.0f}%→{s['opm'] * 100:.0f}%")
        if s["price"] and b.get("price") and s["price"] < b["price"] * 0.75:
            bad.append(f"편입 후 {pct(s['price'] / b['price'] - 1)} (이유 점검)")
    return "✅ thesis 유효" if not bad else "⚠️ thesis 점검: " + ", ".join(bad)


def ownership(t, own, exits):
    p = own.get(t)
    if p:
        chg = "🆕 신규" if p["new"] else ("변동 없음" if abs(p["chg"] or 0) < 0.005 else f"{'▲' if p['chg'] > 0 else '▼'}{abs(p['chg']) * 100:.0f}%")
        return f"13F 비중 {p['w'] * 100:.1f}% ({chg})"
    if t in exits:
        return "13F 전량 매도"
    return "13F 미보유 · 매수 보도(미확인)" if t in WATCH else "13F 미보유"


def build(res, f13, state, week, asof):
    own, exits = f13["pos"], f13["exits"]
    top = res[:10]
    prev_rank = state.get("ranks", {})
    base = state.get("baseline", {})
    head = [f"📅 <b>주간 애크먼 TOP10</b> · {week}",
            f"미국 {asof} 종가 · 13F {f13['date']} (제출 {f13['filed']})", ""]
    for n, s in enumerate(top, 1):
        pr = prev_rank.get(s["t"])
        mv = "🆕" if pr is None else ("" if pr == n else (f"▲{pr - n}" if pr > n else f"▼{n - pr}"))
        head.append(f"{n}. <b>{s['t']}</b> {s['total']:.0f}점 {mv}".rstrip())
        head.append(f"   {money(s['price'])} · 적정 {money(s['fv'])} · 매수 ≤{money(s['buy'])} {status(s)[:1]}")
    out_ = [t for t in prev_rank if t not in [s["t"] for s in top]]
    if out_:
        head += ["", "↘️ TOP10 이탈: " + ", ".join(out_)]
    head += ["", "🟢 매수 구간(적정가 −20% 이하) · 🟡 적정가 이하 · 🔴 적정가 초과 · ⚪ 산출 제외",
             "평가(100점): 매출성장 12 · 순이익성장 12 · 잉여현금흐름 12 · 수익성 16 · 재무건전성 8 · 밸류에이션 10 · "
             "PS 보유 10 · AI·디지털 5 · 경쟁우위 10 · 애크먼 최근 매매 5"]
    blocks = []
    for n, s in enumerate(top, 1):
        t = s["t"]
        th = THESIS.get(t)
        pt = s["pts"]
        b = [f"<b>{n}. {html.escape(s['name'])} ({t}) — {s['total']:.0f}점</b>",
             f"{status(s)} · {ownership(t, own, exits)}",
             f"현재 {money(s['price'])} · 적정 {money(s['fv'])} ({pct(s['up'])}) · 매수 ≤{money(s['buy'])}"
             + (f" · 애널 목표 {money(s['target'])}" if s["target"] else ""),
             f"▪ 근거: 매출 {pct(s['rg'])} · 순이익 {pct(s['ng'])} · 영업이익률 {'-' if s['opm'] is None else f'{s['opm'] * 100:.0f}%'}"
             f" · FCF수익률 {'-' if s['fy'] is None else f'{s['fy'] * 100:.1f}%'} · 선행PER {'-' if not s['fpe'] else f'{s['fpe']:.1f}'}"
             f" · 순부채/EBITDA {'순현금' if s['lev'] < 0 else ('-' if s['lev'] >= 99 else f'{s['lev']:.1f}')}",
             "▪ 점수: " + " · ".join(f"{k} {v:.0f}" for k, v in pt.items())]
        if s["methods"]:
            b.append("▪ 적정가 계산: " + " / ".join(f"{m} {money(v)}" for m, v in s["methods"])
                     + (" (설비투자로 FCF 일시 감소 → 순이익 기준 정상화)" if s["norm"] else ""))
        if th:
            b += [f"▪ thesis: {th[0]}", f"▪ 10년 전망: {th[1]}", f"▪ 위험: {th[2]}"]
        b.append(thesis_check(s, own, base))
        blocks.append("\n".join(b))
    rest = [s for s in res[10:]]
    tail = ["📌 <b>참고</b>"]
    if rest:
        tail.append("11위 이하: " + ", ".join(f"{s['t']} {s['total']:.0f}" for s in rest))
    if f13.get("gone"):
        tail.append("애크먼 직전 분기 전량 매도(순위 제외): " + ", ".join(f"{s['t']} {s['total']:.0f}점 {money(s['price'])}" for s in f13["gone"]))
    tail += ["", "※ 적정주가 = PER법(성장률 반영 PER) · 10년 FCF 할인(DCF, 할인율 9%) · FCF수익률법의 중앙값. "
             "매수가격 = 적정가의 80%(안전마진 20%). 숫자는 yfinance 기준이라 일회성 항목에 흔들릴 수 있음.",
             "※ 13F는 분기말 기준 최대 45일 늦게 공개. 신규 13F는 이 방에 별도 알림. 투자 자문 아님."]
    msgs, cur = ["\n".join(head)], ""
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
        new = ((r.json() if r.headers.get("content-type", "").startswith("application/json") else {}).get("parameters") or {}).get("migrate_to_chat_id")
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
    fixture = json.load(open(sys.argv[sys.argv.index("--fixture") + 1])) if "--fixture" in sys.argv else None
    state = json.load(open(state_path)) if os.path.exists(state_path) else {}
    now = dt.datetime.now(KST)
    y, w, _ = now.isocalendar()
    week = f"{y}-W{w:02d}"
    if do_send and state.get("sent_week") == week and not force:
        print(f"::notice::{week} 이미 전송함 → 건너뜀")
        return

    f13 = ackman_13f()
    print(f"::notice::13F {f13['date']} 매핑 {len(f13['pos'])}종목, 전량매도 {f13['exits']}")
    universe = list(dict.fromkeys(list(f13["pos"]) + WATCH + f13["exits"]))
    res, fail = [], []
    for t in universe:
        try:
            d = fetch(t, fixture)
            if not d["price"]:
                raise ValueError("가격 없음")
            res.append(score(t, d, f13["pos"]))
        except Exception as e:
            fail.append(t)
            print(f"::warning::{t} 데이터 실패: {str(e)[:150]}")
        time.sleep(0.5 if fixture is None else 0)
    if len(res) < max(6, len(universe) // 2):
        print(f"::error::데이터 부족 ({len(res)}/{len(universe)}) → 전송 안 함")
        sys.exit(1)
    res.sort(key=lambda s: -s["total"])
    gone = [s for s in res if s["t"] in f13["exits"]]          # 애크먼이 판 종목은 순위에서 빼고 참고로만
    res = [s for s in res if s["t"] not in f13["exits"]]
    f13["gone"] = gone
    asof = now.date().isoformat() if fixture is None else "fixture"
    try:
        import yfinance as yf
        h = yf.Ticker("SPY").history(period="5d")
        asof = str(h.index[-1].date())
    except Exception:
        pass
    msgs = build(res, f13, state, week, asof)
    for i, m in enumerate(msgs, 1):
        if do_send:
            send(m)
            print(f"::notice::전송 {i}/{len(msgs)}")
            time.sleep(1)
        else:
            print("::notice::" + m.replace("%", "%25").replace("\n", "%0A"))
    if not do_send:
        return
    # 상태(전송 시에만): 순위, 편입 기준값(thesis 점검용), 전송 주차
    base = state.get("baseline", {})
    for s in res[:10]:
        base.setdefault(s["t"], {"date": asof, "price": s["price"], "opm": s["opm"], "rg": s["rg"]})
    state.update({"ranks": {s["t"]: n for n, s in enumerate(res[:10], 1)}, "baseline": base,
                  "last_run": now.isoformat(timespec="minutes"), "sent_week": week})
    json.dump(state, open(state_path, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
