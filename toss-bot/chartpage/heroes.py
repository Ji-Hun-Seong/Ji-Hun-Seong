"""
heroes.py — '내 투자 대가 5인'의 원전 기준으로 종목을 채점 (장기 투자 판단용)

  🛡️ 그레이엄 『현명한 투자자』 방어적 7기준·기업형·넷넷 + 『증권분석』 수익력
  🏰 버핏     주주서한 1977~2007 · 주총 문답 · FCIC 인터뷰 (꾸준한 수익력·ROE·빚·주주 이익·1달러 테스트·가격 결정력·가격)
  🌱 피셔     『위대한 기업에 투자하라』 15가지 + 『보수적인 투자자는 마음이 편하다』 4차원
  🔎 린치     『전설로 떠나는 월가의 영웅』·『이기는 투자』·『Learn to Earn』 — 6분류별 점검표
  🎯 애크먼   퍼싱스퀘어 투자 원칙

세부 기준과 객관화 원칙은 heroes_core.py 머리말 참고. 대가마다 20점, 합계 100점. 등급:
  70↑ 장기 핵심 · 55↑ 장기 위성 · 40↑ 관찰 · 그 아래 장기 부적합
  그레이엄 거름망(10년 내 적자·부채비율 200%↑)에 걸리면 점수와 상관없이 '관찰'까지만.

단독 테스트:  python3 heroes.py 005930 000660
"""
from __future__ import annotations

import math
import os
import re
import time
import sys
from concurrent.futures import ThreadPoolExecutor
import statistics as stx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import heroes_core as HC
from heroes_core import cagr, last

HEROES = [   # (키, 이름, 아이콘, 주제, 한 줄 원칙 — 반영한 원전)
    ("graham", "벤저민 그레이엄", "🛡️", "안전마진", "『현명한 투자자』 방어적 7기준 + 『증권분석』 수익력 — 규모·재무·10년 흑자·20년 배당·이익 성장·PER 15·PBR 1.5"),
    ("buffett", "워런 버핏", "🏰", "해자·ROE", "주주서한(1977~2007)·주총 문답 — 꾸준한 수익력, 빚 없이 높은 ROE, 주주 이익, 1달러 테스트, 가격 결정력, 적당한 가격"),
    ("fisher", "필립 피셔", "🌱", "위대한 기업", "『위대한 기업에 투자하라』 15가지 + 『보수적인 투자자는 마음이 편하다』 4차원 — 성장, 높은 이익률, 저원가, 스스로 번 돈으로 성장"),
    ("lynch", "피터 린치", "🔎", "성장 대비 가격", "『전설로 떠나는 월가의 영웅』·『이기는 투자』·『Learn to Earn』 — 6분류별 점검표, (성장+배당)/PER, 재무, 과열 피하기"),
    ("ackman", "빌 애크먼", "🎯", "촉매·환원", "퍼싱스퀘어 원칙 — 단순·예측 가능·FCF 창출, 진입장벽, 튼튼한 재무, 매력적 가격, 가치가 드러날 계기"),
]

# 화면에 보여 줄 나의 원칙 (대시보드 홈·발굴 탭)
PRINCIPLES = {
    "mix": {"target_short": 0.10, "max_short": 0.20,
            "text": "장기 투자 9 : 단기 매매 1 — 단기는 많아도 2를 넘기지 않는다 (안정성 우선)"},
    "iron": [   # 어떤 상황에서도 지키는 철칙 (대시보드 홈 맨 위에 항상 표시)
        "절대 대출(신용·미수·주식담보대출·마이너스통장)해서 투자하지 않는다",
        "FOMO에 흔들리지 않는다 — 이미 급등한 종목은 쫓지 않고 원칙에 맞는 가격까지 기다린다",
    ],
    "rules": [
        ("린치", "종목 찾기", "생활·업무에서 아는 회사에서 출발하고, 왜 오를지 두 문장으로 말할 수 있어야 산다"),
        ("그레이엄", "거름망", "적자 연도가 있거나 부채비율 200%↑면 장기 바구니에 넣지 않는다"),
        ("버핏·피셔", "품질", "ROE 15%↑를 꾸준히, 매출과 이익이 함께 크는 회사를 고른다"),
        ("그레이엄·린치", "가격", "좋은 회사라도 비싸면 기다린다 — PER×PBR ≤ 22.5 또는 PEG ≤ 1"),
        ("애크먼", "촉매", "자사주 소각·배당·지배구조 개선 등 재평가 계기가 있는지 확인한다"),
    ],
    "portfolio": [
        "장기 바구니 안: 핵심(버핏·피셔형) 70% · 위성(그레이엄 자산주·애크먼 촉매주) 30%",
        "12~15종목, 한 종목은 장기 자산의 15%까지",
        "매도: 핵심은 산 이유가 깨질 때만 · 위성은 가치에 도달하면 · 단기는 정해진 규칙대로",
    ],
}

GRADES = [
    (70, "core", "🟢 장기 핵심", "핵심 바구니(70%) 후보 · 3년 이상 보유 전제"),
    (55, "sat", "🟡 장기 위성", "위성 바구니(30%) 후보 · 목표 가치에 닿으면 매도"),
    (40, "watch", "⚪ 관찰", "관찰 목록 · 가격이나 실적이 좋아질 때까지 기다림"),
    (-1, "no", "🔴 장기 부적합", "장기 바구니 X · 단기 매매(전체의 10% 이내) 대상만"),
]

LYNCH_SELL = {
    "고성장주": "성장률이 꺾이거나 PER이 성장률의 2배를 넘으면 정리",
    "대형우량주": "30~50% 오르면 일부 차익, 다른 우량주로 교체",
    "저성장주": "배당을 깎거나 시장점유율을 잃으면 정리",
    "경기순환주": "업황 정점(이익 최고·PER 최저)에서 정리 — 장기 보유 금지",
    "회생주": "회생이 끝나 평범한 회사가 되면 정리",
    "자산주": "자산 가치가 주가에 반영되면 정리",
    "보통주(중간)": "산 이유가 유지되는지 분기마다 점검",
}


# ── 작은 도우미 ─────────────────────────────────────────
def _ok(v):
    return v is not None and not (isinstance(v, float) and (math.isnan(v) or math.isinf(v)))


def _series(fin: dict, row: str, est: bool = False) -> list[float]:
    """연간 재무의 한 행 → 실제(또는 추정) 값만, 오래된 → 최신"""
    a = (fin or {}).get("annual") or {}
    vals = (a.get("rows") or {}).get(row) or []
    ps = a.get("periods") or []
    return [v for v, p in zip(vals, ps) if _ok(v) and bool(p.get("est")) == est]


def _cagr(first, last, years):
    if not (_ok(first) and _ok(last)) or first <= 0 or last <= 0 or years <= 0:
        return None
    return (last / first) ** (1 / years) - 1


def _chk(pts, mx, text, ok=None, na=False):
    """ok=None → 데이터 없음: 반만 준 것으로 계산(없는 정보로 만점이 되지 않게)
       na=True → 이 종목엔 해당 없는 기준(금융업 부채비율·해외 종목 DART 공시): 계산에서 아예 뺌"""
    return {"pts": pts if ok is not None else 0, "max": mx, "ok": ok, "text": text, "na": na}


def _last(x, n):
    return [v for v in (x or []) if v is not None][-n:]


def _lastv(x):
    v = _last(x, 1)
    return v[0] if v else None


_DART_K = {"rev": "매출액", "op": "영업이익", "ni": "당기순이익", "nio": "지배순이익", "eps": "EPS", "dps": "DPS", "eq": "자본총계",
           "eqo": "지배자본", "liab": "부채총계", "ca": "유동자산", "cl": "유동부채", "inv": "재고자산", "ncl": "비유동부채", "cash": "현금성자산",
           "netcash": "순현금", "ocf": "영업CF", "fcf": "FCF", "capex": "CAPEX", "roe": "ROE", "opm": "영업이익률", "dr": "부채비율",
           "cr": "유동비율", "payout": "배당성향", "yclose": "연말 주가", "per_y": "PER"}
_NAVER_K = {"rev": "매출액", "op": "영업이익", "ni": "당기순이익", "eps": "EPS", "dps": "주당배당금", "roe": "ROE", "opm": "영업이익률",
            "dr": "부채비율", "cr": "유동비율", "payout": "배당성향"}


def _facts(d: dict) -> dict:
    """채점용 숫자 모음. by[k] = {연도: 값} (한국은 DART 최대 10년, 아니면 네이버/야후 연간 4년)
       리스트형 F[k] 는 값 있는 해만 오래된 → 최신"""
    us = bool(d.get("us"))
    P = d.get("profile") or {}
    fin = d.get("finance") or {}
    ok = lambda v: v if _ok(v) else None
    F = {"us": us, "per": ok(P.get("per")), "pbr": ok(P.get("pbr")), "dy": ok(P.get("div_yield")),
         "mcap_eok": ok(P.get("mcap_eok")) or (P["mcap_usd"] * 1400 / 1e8 if _ok(P.get("mcap_usd")) else None),
         "close": ok((d.get("tech") or {}).get("close")) or ok(d.get("close")), "target": ok(P.get("target")),
         "eps_est": _series(fin, "EPS", est=True), "src": "naver"}
    by = {}
    dart = d.get("dart") or {}
    if dart.get("labels") and dart.get("key") and not dart.get("error"):
        labs = dart["labels"]
        for k, nm in _DART_K.items():
            v = dart["key"].get(nm) or []
            by[k] = {labs[i]: v[i] for i in range(min(len(v), len(labs))) if labs[i].isdigit() and _ok(v[i])}
        F["src"] = "dart"
    else:
        a = fin.get("annual") or {}
        ps, rows = a.get("periods") or [], a.get("rows") or {}
        yrs = [(re.match(r"(\d{4})", p.get("title") or "") or [None, None])[1] if not p.get("est") else None for p in ps]
        for k, nm in _NAVER_K.items():
            vals = rows.get(nm) or []
            by[k] = {y: v for y, v in zip(yrs, vals) if y and _ok(v)}
        if not by.get("roe") and _ok(P.get("roe")):
            by["roe"] = {"now": P["roe"] * 100}
        if not by.get("opm") and _ok(P.get("opm")):
            by["opm"] = {"now": P["opm"] * 100}
        if not by.get("dr") and _ok(P.get("de")):
            by["dr"] = {"now": P["de"]}
    # 연말 종가 — DART에 없으면 일봉에서
    oh = d.get("ohlc") or {}
    if oh.get("d") and oh.get("c"):
        ye = {}
        for dt, c in zip(oh["d"], oh["c"]):
            if c:
                ye[dt[:4]] = c
        if not by.get("yclose"):
            by["yclose"] = ye
        cs = [c for c in oh["c"] if c]
        F["ret1y"] = cs[-1] / cs[-250] - 1 if len(cs) > 250 and cs[-250] else None
        F["close"] = F["close"] or (cs[-1] if cs else None)
    else:
        F["ret1y"] = None
    # 주식 수 = 지배순이익 ÷ EPS (희석·1달러 테스트용)
    nio = by.get("nio") or by.get("ni") or {}
    by["shares"] = {y: nio[y] * 1e8 / e for y, e in (by.get("eps") or {}).items() if y in nio and e and e > 0 and nio[y] > 0} if F["src"] == "dart" else {}
    by.setdefault("nio", dict(by.get("ni") or {}))
    for k in set(_DART_K) | {"shares"}:
        by.setdefault(k, {})
        F[k] = [by[k][y] for y in sorted(by[k])]
    F["by"] = by
    # 금융업 판정(부채비율 500%↑·흑자) · ROE 평균
    ra = last(F["roe"], 10)
    F["roe_avg"] = sum(ra) / len(ra) if ra else None
    F["fin_co"] = bool(F["dr"]) and F["dr"][-1] > 500 and (F["roe_avg"] or 0) > 0
    # 이익 성장률(린치) — 최근 5년 EPS 연평균, 안 되면 순이익
    e = last(F["eps"], 6)
    eg = cagr(e[0], e[-1], len(e) - 1) if len(e) >= 3 else None
    if eg is None:
        n = last(F["ni"], 6)
        eg = cagr(n[0], n[-1], len(n) - 1) if len(n) >= 3 else None
    if eg is None and len(e) >= 3 and e[-1] <= e[0]:
        eg = -0.01 if e[-1] > 0 else None
    F["eg"] = eg
    # 현재 PER vs 자기 과거 PER 중간값 (그해 말 주가 ÷ 그해 EPS)
    hist = [v for y, v in sorted(by["per_y"].items())[:-1] if v and v > 0] if by["per_y"] else \
           [by["yclose"][y] / by["eps"][y] for y in sorted(by["eps"])[:-1] if y in by["yclose"] and by["eps"][y] and by["eps"][y] > 0]
    hist = hist[-7:]
    F["per_hist_n"] = len(hist)
    F["per_rel"] = F["per"] / stx.median(hist) if F["per"] and F["per"] > 0 and len(hist) >= 3 else None
    return F


# ── 5인 채점 ───────────────────────────────────────────
def score(d: dict) -> dict:
    """d = stock_info 상세(또는 board용 가벼운 dict). 반환: 대가별 점수·체크(출처·기준선)·등급·린치 분류"""
    F = _facts(d)
    filings = d.get("filings")
    has_f = (not F["us"]) and filings is not None and d.get("filings_ok", True)
    H, T = {}, {}
    H["graham"], T["graham"], graham_fail = HC.graham(F)
    H["buffett"], T["buffett"] = HC.buffett(F)
    H["fisher"], T["fisher"] = HC.fisher(F)
    H["lynch"], T["lynch"], cat = HC.lynch(F)
    H["ackman"], T["ackman"] = HC.ackman(F, filings or [], has_f)

    heroes, got, mx_all, av_all = [], 0, 0, 0
    for key, name, icon, theme, motto in HEROES:
        cs = H[key]
        sc = [c for c in cs if not c.get("na") and not c.get("bonus")]
        ev = [c for c in sc if c["ok"] is not None]
        p, m, mm = sum(c["pts"] for c in ev), len(ev), len(sc) - len(ev)
        n_orig = sum(1 for c in sc if c.get("orig"))
        base = {"key": key, "name": name, "icon": icon, "theme": theme, "motto": motto, "checks": cs, "todo": T.get(key, []),
                "n": len(sc), "n_orig": n_orig}
        if m == 0:
            heroes.append({**base, "score": None, "coverage": 0})
            continue
        p2, m2 = p + 0.5 * mm, m + mm                 # 같은 비중 · 데이터 없는 항목은 반만 인정
        got, mx_all, av_all = got + p2 / m2 * 20, mx_all + 20, av_all + m / m2 * 20
        heroes.append({**base, "score": round(p2 / m2 * 20, 1), "coverage": round(m / m2, 2)})
    total = round(got / mx_all * 100, 1) if mx_all else None
    coverage = av_all / mx_all if mx_all else 0
    if graham_fail and (total is None or coverage < 0.5):
        grade = {"key": "no", "label": GRADES[3][2], "desc": "적자 연도·부채 과다(그레이엄 거름망 탈락) — " + GRADES[3][3]}
    elif total is None or coverage < 0.5:
        grade = {"key": "na", "label": "⚪ 데이터 부족", "desc": "판단에 필요한 재무 데이터가 절반 미만"}
    else:
        gk = next(g for g in GRADES if total >= g[0])
        if graham_fail and gk[1] in ("core", "sat"):
            gk = GRADES[2]
            grade = {"key": gk[1], "label": gk[2], "desc": "그레이엄 거름망 탈락(최근 10년 적자 연도·부채비율 200%↑) — 점수와 상관없이 관찰까지만"}
        else:
            grade = {"key": gk[1], "label": gk[2], "desc": gk[3]}
    q = sum(h["score"] or 0 for h in heroes if h["key"] in ("buffett", "fisher"))
    pr = sum(h["score"] or 0 for h in heroes if h["key"] in ("graham", "lynch"))
    note = None
    if q >= 28 and pr < 16:
        note = "🏰 품질(버핏·피셔)은 좋은데 가격(그레이엄·린치)이 비쌈 → 좋은 회사 목록에 두고 가격이 내려오길 기다리기"
    elif pr >= 28 and q < 16:
        note = "🛡️ 싸지만 품질이 약함 → 핵심이 아닌 위성(자산주)으로만, 가치에 닿으면 매도"
    return {"total": total, "coverage": round(coverage, 2), "grade": grade, "note": note, "heroes": heroes, "src": F["src"],
            "lynch_cat": cat, "lynch_sell": LYNCH_SELL.get(cat), "fin_co": F["fin_co"], "method": METHOD}


METHOD = ("📖 = 책·주주서한에 나온 숫자 그대로 · ⚖️ = 원전에 숫자가 없어 정한 보조선(화면에 기준 공개). "
          "점수는 0점 선과 만점 선 사이를 직선으로, 한 대가 안의 항목은 같은 비중, 데이터 없는 항목은 반만 인정")


# ── 발굴 탭: 후보 묶음을 한꺼번에 채점 ─────────────────────
def light(code: str, name: str | None = None, corp_code: str | None = None) -> dict:
    """목록용 가벼운 데이터 — 밸류(1회) + 연간 재무(1회) + 공시(1회). 시세 일봉은 받지 않음"""
    import stock_info as si
    prof = si.kr_profile(code)
    fa = si.kr_finance(code, "annual")
    filings, fok = [], False
    try:
        if corp_code and (os.environ.get("DART_API_KEY") or os.environ.get("DART_KEY")):
            filings, fok = si.kr_filings(corp_code), True
    except Exception:
        pass
    dart = None
    try:                                              # DART 10년 재무(한 번 받으면 디스크에 저장돼서 다음부턴 빠름)
        if corp_code and (os.environ.get("DART_API_KEY") or os.environ.get("DART_KEY")):
            import dart_fin
            dart = dart_fin.build(corp_code)
    except Exception:
        dart = None
    close = None
    try:                                              # 종가: 네이버 integration 에는 없어서 연간 재무 대신 목표가 여력용으로만 씀
        close = si.num((si._get(f"{si.NAVER}/{code}/basic").json() or {}).get("closePrice"))
    except Exception:
        pass
    return {"us": False, "code": code, "name": prof.get("name") or name or code, "profile": prof,
            "finance": {"annual": fa}, "filings": filings, "filings_ok": fok, "close": close, "dart": dart}


# ── 해외 시장별 후보 (발굴 › 대가 › 국가 탭) — 대표 우량주 + 가치·배당주 + 애크먼 계열 ─────────
GLOBAL_POOL = {
    "us": [("AAPL", "애플"), ("MSFT", "마이크로소프트"), ("NVDA", "엔비디아"), ("GOOGL", "알파벳"), ("AMZN", "아마존"), ("META", "메타"),
           ("BRK-B", "버크셔해서웨이"), ("AVGO", "브로드컴"), ("LLY", "일라이릴리"), ("JPM", "JP모건"), ("V", "비자"), ("MA", "마스터카드"),
           ("COST", "코스트코"), ("WMT", "월마트"), ("HD", "홈디포"), ("PG", "P&G"), ("KO", "코카콜라"), ("PEP", "펩시코"),
           ("JNJ", "존슨앤존슨"), ("MRK", "머크"), ("UNH", "유나이티드헬스"), ("XOM", "엑슨모빌"), ("CVX", "셰브론"), ("CAT", "캐터필러"),
           ("ORCL", "오라클"), ("ADBE", "어도비"), ("QCOM", "퀄컴"), ("TXN", "텍사스인스트루먼트"), ("MCD", "맥도날드"), ("NKE", "나이키"),
           ("CMG", "치폴레"), ("QSR", "레스토랑브랜즈"), ("HLT", "힐튼"), ("HHH", "하워드휴즈"), ("BN", "브룩필드"), ("UBER", "우버"),
           ("GOOG", "알파벳C"), ("BAC", "뱅크오브아메리카"), ("ABBV", "애브비"), ("MO", "알트리아"), ("VZ", "버라이즌"), ("PFE", "화이자")],
    "eu": [("ASML.AS", "ASML"), ("MC.PA", "LVMH"), ("RMS.PA", "에르메스"), ("OR.PA", "로레알"), ("TTE.PA", "토탈에너지"), ("SAN.PA", "사노피"),
           ("SU.PA", "슈나이더"), ("AIR.PA", "에어버스"), ("SAP.DE", "SAP"), ("SIE.DE", "지멘스"), ("ALV.DE", "알리안츠"), ("MBG.DE", "메르세데스"),
           ("BMW.DE", "BMW"), ("VOW3.DE", "폭스바겐"), ("RHM.DE", "라인메탈"), ("IFX.DE", "인피니언"), ("NESN.SW", "네슬레"), ("ROG.SW", "로슈"),
           ("NOVN.SW", "노바티스"), ("UBSG.SW", "UBS"), ("NOVO-B.CO", "노보노디스크"), ("SHEL.L", "셸"), ("AZN.L", "아스트라제네카"),
           ("HSBA.L", "HSBC"), ("ULVR.L", "유니레버"), ("BP.L", "BP"), ("RIO.L", "리오틴토"), ("BA.L", "BAE시스템스"), ("RR.L", "롤스로이스"),
           ("RACE.MI", "페라리"), ("ITX.MC", "인디텍스"), ("UMG.AS", "유니버설뮤직"), ("EQNR.OL", "에퀴노르"), ("VOLV-B.ST", "볼보")],
    "cn": [("600519.SS", "귀주모태"), ("300750.SZ", "CATL"), ("601318.SS", "중국평안"), ("600036.SS", "초상은행"), ("601398.SS", "공상은행"),
           ("000858.SZ", "오량액"), ("000333.SZ", "메이디"), ("600276.SS", "항서제약"), ("600900.SS", "장강전력"), ("600887.SS", "이리"),
           ("601088.SS", "중국신화에너지"), ("601899.SS", "자금광업"), ("002415.SZ", "하이크비전"), ("002475.SZ", "럭스셰어"), ("603288.SS", "해천미업"),
           ("0700.HK", "텐센트"), ("9988.HK", "알리바바"), ("3690.HK", "메이퇀"), ("1810.HK", "샤오미"), ("1211.HK", "BYD"),
           ("9618.HK", "징둥"), ("9888.HK", "바이두"), ("9999.HK", "넷이즈"), ("0941.HK", "차이나모바일"), ("0883.HK", "CNOOC"),
           ("0939.HK", "중국건설은행"), ("1299.HK", "AIA"), ("0388.HK", "홍콩거래소"), ("2020.HK", "안타스포츠"), ("9961.HK", "트립닷컴")],
    "jp": [("7203.T", "토요타"), ("6758.T", "소니"), ("7974.T", "닌텐도"), ("6861.T", "키엔스"), ("8035.T", "도쿄일렉트론"), ("9984.T", "소프트뱅크그룹"),
           ("9983.T", "패스트리테일링"), ("8306.T", "미쓰비시UFJ"), ("8058.T", "미쓰비시상사"), ("8031.T", "미쓰이물산"), ("8001.T", "이토추"),
           ("8053.T", "스미토모상사"), ("8002.T", "마루베니"), ("7267.T", "혼다"), ("6501.T", "히타치"), ("4063.T", "신에쓰화학"),
           ("6857.T", "어드반테스트"), ("6367.T", "다이킨"), ("6954.T", "화낙"), ("6981.T", "무라타"), ("9432.T", "NTT"), ("9433.T", "KDDI"),
           ("2914.T", "JT"), ("4502.T", "다케다"), ("7011.T", "미쓰비시중공업"), ("6098.T", "리쿠르트"), ("8766.T", "도쿄해상"),
           ("8316.T", "스미토모미쓰이"), ("7936.T", "아식스"), ("7832.T", "반다이남코"), ("9697.T", "캡콤"), ("4661.T", "오리엔탈랜드")],
}
MARKET_NAME = {"kr": "🇰🇷 한국", "us": "🇺🇸 미국", "eu": "🇪🇺 유럽", "cn": "🇨🇳 중국·홍콩", "jp": "🇯🇵 일본"}
_FX = {}


def _krw_per(ccy: str) -> float | None:
    """통화 1단위 = 몇 원 (GBp·ZAc 같은 1/100 단위 보정)"""
    if not ccy:
        return None
    if ccy == "KRW":
        return 1.0
    unit = 0.01 if ccy in ("GBp", "ZAc", "ILA") else 1.0
    base = {"GBp": "GBP", "ZAc": "ZAR", "ILA": "ILS"}.get(ccy, ccy)
    hit = _FX.get(base)
    if hit and time.time() - hit[0] < 6 * 3600:
        return hit[1] * unit
    try:
        import data_sources as ds
        df = ds._yahoo(f"{base}KRW=X", "1mo")
        v = float(df["close"].iloc[-1])
    except Exception:
        v = {"USD": 1400, "JPY": 9.3, "EUR": 1500, "GBP": 1800, "CNY": 195, "HKD": 180, "CHF": 1600}.get(base)
    if v:
        _FX[base] = (time.time(), v)
    return v * unit if v else None


def light_global(sym: str, name: str | None = None) -> dict:
    """해외 목록용 가벼운 데이터 — yfinance info + 연간 손익 (일봉은 받지 않음)"""
    import yfinance as yf
    import stock_info as si
    tk = yf.Ticker(sym)
    info = tk.info or {}
    g = info.get
    price = g("currentPrice") or g("regularMarketPrice") or g("previousClose")
    rate = g("dividendRate") or g("trailingAnnualDividendRate")
    dy = rate / price * 100 if rate and price else (g("trailingAnnualDividendYield") or 0) * 100
    if dy and dy > 25:                                 # 통화 단위가 어긋난 경우(펜스 등)
        dy /= 100
    ccy = g("currency")
    fx = _krw_per(ccy)
    mcap = g("marketCap")
    prof = {"name": name or g("shortName") or sym, "per": g("trailingPE"), "fper": g("forwardPE"), "pbr": g("priceToBook"),
            "div_yield": dy, "roe": g("returnOnEquity"), "opm": g("operatingMargins"), "de": g("debtToEquity"),
            "target": g("targetMeanPrice"), "mcap_usd": mcap, "currency": ccy,
            "mcap_eok": mcap * fx / 1e8 if mcap and fx else None}
    fin = {}
    try:
        fin["annual"] = si.yf_annual(tk)                 # 4년치 영업이익률·ROE·부채비율까지 (꾸준함 판단용)
    except Exception:
        pass
    return {"us": True, "code": sym, "name": prof["name"], "profile": prof, "finance": fin, "filings": None, "close": price}


def board(pool: list[dict], workers: int = 8, market: str = "kr") -> dict:
    """pool = [{code, name, corp_code, src:[...], held}] → 점수 순 목록 (market != kr 이면 해외 yfinance)"""
    def one(p):
        try:
            d = light(p["code"], p.get("name"), p.get("corp_code")) if market == "kr" else light_global(p["code"], p.get("name"))
            s = score(d)
            P = d["profile"]
            return {"code": p["code"], "name": d["name"], "src": p.get("src", []), "held": p.get("held", False),
                    "us": market != "kr", "ccy": (d["profile"] or {}).get("currency"),
                    "total": s["total"], "grade": s["grade"], "note": s["note"], "lynch_cat": s["lynch_cat"],
                    "heroes": {h["key"]: h["score"] for h in s["heroes"]},
                    "best": [c["text"] for h in s["heroes"] for c in h["checks"] if c["ok"] is True and not c.get("bonus")][:3],
                    "worst": [c["text"] for h in s["heroes"] for c in h["checks"] if c["ok"] is False][:2],
                    "per": P.get("per"), "pbr": P.get("pbr"), "yield": P.get("div_yield"), "mcap_eok": P.get("mcap_eok")}
        except Exception as e:
            return {"code": p["code"], "name": p.get("name") or p["code"], "error": f"{type(e).__name__}: {str(e)[:80]}"}
    with ThreadPoolExecutor(workers) as ex:
        rows = list(ex.map(one, pool))
    ok = [r for r in rows if r.get("total") is not None and r["grade"]["key"] != "na"]
    ok.sort(key=lambda r: -r["total"])
    for i, r in enumerate(ok, 1):
        r["rank"] = i
    cnt = {}
    for r in ok:
        cnt[r["grade"]["key"]] = cnt.get(r["grade"]["key"], 0) + 1
    return {"items": ok, "failed": [r for r in rows if r not in ok], "n_pool": len(pool), "grades": cnt, "market": market,
            "market_name": MARKET_NAME.get(market, market)}


if __name__ == "__main__":
    import json
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import stock_info as si
    for q in sys.argv[1:] or ["005930"]:
        r = score(si.detail({"code": q, "us": not q.isdigit()}))
        print(q, r["total"], r["grade"]["label"], r["lynch_cat"], r["note"] or "")
        for h in r["heroes"]:
            print(f"  {h['icon']} {h['name']} {h['score']}/20")
            for c in h["checks"]:
                print(f"     {'✅' if c['ok'] else '❌' if c['ok'] is False else '·'} {c['text']}")
