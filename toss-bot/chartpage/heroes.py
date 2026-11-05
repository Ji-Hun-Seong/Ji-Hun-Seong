"""
heroes.py — 대가 10인(가치 5 · 성장 5)의 원전 기준으로 종목을 채점 (장기 투자 판단용)

  💎 가치주 5인                                       🚀 성장주 5인
  🏰 버핏      해자·ROE (주주서한·주총 문답)            🔎 린치        성장 대비 가격 (6분류 점검표)
  🛡️ 그레이엄  안전마진 (『현명한 투자자』·『증권분석』)   🌱 피셔        위대한 성장 기업 (15가지 + 4차원)
  🧠 멍거      훌륭한 기업을 공정한 가격에 (ROE 18%)     🦅 드러켄밀러  18개월 뒤 이익·가격 흐름·자본 보존
  🎯 애크먼    촉매·환원 (퍼싱스퀘어 원칙)              🌍 템플턴      미래 이익 대비 가격·최대 비관
  🔒 클라만    보수적 가치 범위 대비 안전마진            📈 로 프라이스  이익이 사이클마다 새 고점·성장의 계절

대가마다 20점 → 5명 합 = 가치 점수 100 · 성장 점수 100 을 따로 냄. 종목 등급은 둘 중 높은 쪽 기준:
  70↑ 장기 핵심 · 55↑ 장기 위성 · 40↑ 관찰 · 그 아래 장기 부적합
  가치 쪽 거름망 = 그레이엄(10년 내 적자·부채비율 200%↑) · 성장 쪽 거름망 = 매출·이익 성장 5% 미만 또는 최근 3년 적자·부채비율 200%↑
  → 거름망에 걸린 쪽 점수로는 '관찰'까지만.
  대가 동의 수 = 그 쪽 5명 중 14점(70%)↑ 준 사람 수 — 핵심(70점↑)은 3명 이상이 동의해야 유지, 아니면 위성으로 한 단계 내림
세부 기준과 객관화 원칙은 heroes_core.py 머리말 참고.

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

HEROES = [   # (키, 이름, 아이콘, 주제, 한 줄 원칙 — 반영한 원전, 유형 value/growth) — 사진 순서(가치 TOP 5 · 성장 TOP 5)
    ("buffett", "워런 버핏", "🏰", "해자·ROE", "주주서한(1977~2007)·주총 문답 — 꾸준한 수익력, 빚 없이 높은 ROE, 주주 이익, 1달러 테스트, 가격 결정력, 적당한 가격", "value"),
    ("graham", "벤저민 그레이엄", "🛡️", "안전마진", "『현명한 투자자』 방어적 7기준 + 『증권분석』 수익력 — 규모·재무·10년 흑자·20년 배당·이익 성장·PER 15·PBR 1.5", "value"),
    ("munger", "찰리 멍거", "🧠", "훌륭한 기업·공정한 가격", "『가난한 찰리의 연감』·USC 1994 강연·'오판의 심리학' — 장기 ROE 18%, 해자 지속, 복리 재투자, 뒤집어 보기(현금 없는 이익·레버리지·희석 회피), ROE만큼 가격 허용", "value"),
    ("ackman", "빌 애크먼", "🎯", "촉매·환원", "퍼싱스퀘어 원칙 — 단순·예측 가능·FCF 창출, 진입장벽, 튼튼한 재무, 매력적 가격, 가치가 드러날 계기", "value"),
    ("klarman", "세스 클라만", "🔒", "보수적 안전마진", "『안전마진』·바우포스트 서한 — 자산·수익·현금흐름 가치 중간값보다 33% 싸게, 5년 평균 FCF, 하방 받침, 재무 생존력, 소외 종목, 가치 함정 회피", "value"),
    ("lynch", "피터 린치", "🔎", "성장 대비 가격", "『전설로 떠나는 월가의 영웅』·『이기는 투자』 — 6분류별 점검표, (성장+배당)/PER, PEG, 재무, 과열 피하기", "growth"),
    ("fisher", "필립 피셔", "🌱", "위대한 성장 기업", "『위대한 기업에 투자하라』 15가지 + 『보수적인 투자자는 마음이 편하다』 4차원 — 평균보다 훨씬 빠른 성장, 업계 최고 이익률, 스스로 번 돈으로 성장 (매출 성장 5% 미만이면 최대 40%)", "growth"),
    ("druckenmiller", "스탠리 드러켄밀러", "🦅", "18개월 뒤·추세", "『새로운 시장의 마법사들』·로스트트리 강연·국부펀드 인터뷰 — 18개월 뒤 이익, 이익 변곡, 가격 흐름(200일선), 주도주, 자본 보존(낙폭)", "growth"),
    ("templeton", "존 템플턴", "🌍", "비관 속 바겐", "16계명·『템플턴 플랜』·『가치투자 전략』 — PER을 자기 5년 평균과, 5년 평균 이익 PER, 5년 뒤 이익 대비 가격, 최대 비관, 우량주 속 바겐", "growth"),
    ("price", "T. 로 프라이스", "📈", "장기 성장주", "성장주 투자의 아버지(1939 '성장주 고르기'·1973 'New Era') — 이익이 경기 사이클마다 새 고점, 높은 자본이익률, 이익률 유지, 과한 값 안 냄, 성장의 계절", "growth"),
]
STYLES = {"value": ("💎", "가치"), "growth": ("🚀", "성장")}


def hero_meta() -> list[dict]:
    """대시보드로 보낼 대가 목록"""
    return [{"key": k, "name": n, "icon": i, "theme": th, "motto": m, "style": s} for k, n, i, th, m, s in HEROES]


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
        ("가치 5인", "가치주", "버핏·그레이엄·멍거·애크먼·클라만 — 좋은 회사를 보수적으로 잡은 가치보다 싸게, 가치에 닿으면 판다"),
        ("성장 5인", "성장주", "린치·피셔·드러켄밀러·템플턴·로 프라이스 — 경제보다 훨씬 빨리 크는 회사를 18개월 뒤 이익 기준으로, 성장이 꺾이면 판다"),
        ("멍거·클라만", "뒤집어 보기", "사기 전에 '어떻게 잃을 수 있나'부터 — 빚·희석·현금 없는 이익·가치 함정이면 사지 않는다"),
        ("그레이엄·린치", "가격", "좋은 회사라도 비싸면 기다린다 — 가치주는 PER×PBR ≤ 22.5, 성장주는 PEG ≤ 1"),
        ("애크먼", "촉매", "자사주 소각·배당·지배구조 개선 등 재평가 계기가 있는지 확인한다"),
    ],
    "portfolio": [
        "장기 바구니 안: 핵심(가치 또는 성장 70점↑) 70% · 위성(55점↑ — 그레이엄 자산주·애크먼 촉매주·드러켄밀러 주도주·템플턴 비관 바겐) 30%",
        "가치형과 성장형을 섞어 담는다 — 한쪽 스타일만 담으면 그 스타일이 안 먹히는 해에 같이 빠진다",
        "12~15종목, 한 종목은 장기 자산의 15%까지",
        "매도: 핵심은 산 이유가 깨질 때만 · 위성은 가치에 도달하면 · 단기는 정해진 규칙대로",
    ],
}

AGREE_PT, AGREE_MIN = 14, 3      # 대가 동의 = 20점 중 14점↑ · 핵심 등급은 5명 중 3명 이상 동의해야

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
        # 드러켄밀러 — 200일 평균 대비 위치 · 최근 1년 최대 낙폭 / 템플턴 — 52주 최고가(프로필에 없을 때)
        F["ma200_gap"] = cs[-1] / (sum(cs[-200:]) / 200) - 1 if len(cs) >= 200 else None
        if len(cs) >= 120:
            pk, mdd = 0.0, 0.0
            for c in cs[-250:]:
                pk = max(pk, c)
                mdd = max(mdd, 1 - c / pk)
            F["mdd1y"] = mdd
        F["hi52_oh"] = max(cs[-250:]) if cs else None
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
    # 분기 EPS(드러켄밀러 이익 변곡) — 네이버 분기 재무 실제치만, 오래된 → 최신
    q = (fin.get("quarter") or {})
    qr, qp = (q.get("rows") or {}), (q.get("periods") or [])
    qv = qr.get("EPS") or qr.get("당기순이익") or []
    F["q_eps"] = [v for v, pp in zip(qv, qp) if _ok(v) and not pp.get("est")]
    F["q_yoy"] = ok(P.get("q_yoy"))
    F["hi52"] = ok(P.get("hi52")) or F.get("hi52_oh")
    F["fper"] = ok(P.get("fper"))
    F.setdefault("ma200_gap", None)
    F.setdefault("mdd1y", None)
    if F["ret1y"] is None and _ok(P.get("ret1y")):
        F["ret1y"] = P["ret1y"]
    F["roc_now"], F["ey_now"] = ok(P.get("roc")), ok(P.get("ey"))
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
    h5 = hist[-5:]                                    # 템플턴 — 최근 5년 평균 PER 과 비교
    F["per_rel5"] = F["per"] / (sum(h5) / len(h5)) if F["per"] and F["per"] > 0 and len(h5) >= 3 else None
    hist = hist[-7:]
    F["per_hist_n"] = len(hist)
    F["per_rel"] = F["per"] / stx.median(hist) if F["per"] and F["per"] > 0 and len(hist) >= 3 else None
    return F


# ── 10인 채점 (가치 5 · 성장 5) ───────────────────────────────────────────
def score(d: dict) -> dict:
    """d = stock_info 상세(또는 board용 가벼운 dict). 반환: 대가별 점수·체크(출처·기준선), 가치·성장 점수와 등급, 린치 분류"""
    F = _facts(d)
    filings = d.get("filings")
    has_f = (not F["us"]) and filings is not None and d.get("filings_ok", True)
    H, T = {}, {}
    H["graham"], T["graham"], graham_fail = HC.graham(F)
    H["buffett"], T["buffett"] = HC.buffett(F)
    H["fisher"], T["fisher"], fisher_cap = HC.fisher(F)
    H["lynch"], T["lynch"], cat = HC.lynch(F)
    H["ackman"], T["ackman"] = HC.ackman(F, filings or [], has_f)

    H["munger"], T["munger"] = HC.munger(F)
    H["klarman"], T["klarman"] = HC.klarman(F)
    H["druckenmiller"], T["druckenmiller"] = HC.druckenmiller(F)
    H["templeton"], T["templeton"] = HC.templeton(F)
    H["price"], T["price"] = HC.price(F)
    caps = {"fisher": fisher_cap}
    if cat in ("저성장주", "자산주"):                    # 린치 본인도 이 두 분류는 '성장'으로 사지 않음 → 성장 트랙에선 최대 50%
        caps["lynch"] = 0.5
        H["lynch"].append(HC.C("『전설로 떠나는 월가의 영웅』 7장", f"🚧 린치 분류가 {cat} — 배당·자산 가치로 사는 종목이라 성장 점수에선 최대 50%", None, bonus=True))

    heroes, acc = [], {"value": [0, 0, 0], "growth": [0, 0, 0]}     # 점수 합 · 만점 합 · 데이터 반영 합
    agree = {"value": 0, "growth": 0}                                # 14점(70%)↑ 준 대가 수
    for key, name, icon, theme, motto, style in HEROES:
        cs = H[key]
        sc = [c for c in cs if not c.get("na") and not c.get("bonus")]
        ev = [c for c in sc if c["ok"] is not None]
        p, m, mm = sum(c["pts"] for c in ev), len(ev), len(sc) - len(ev)
        n_orig = sum(1 for c in sc if c.get("orig"))
        base = {"key": key, "name": name, "icon": icon, "theme": theme, "motto": motto, "style": style, "checks": cs,
                "todo": T.get(key, []), "n": len(sc), "n_orig": n_orig}
        if m == 0:
            heroes.append({**base, "score": None, "coverage": 0})
            continue
        r = (p + 0.5 * mm) / (m + mm)                  # 같은 비중 · 데이터 없는 항목은 반만 인정
        if caps.get(key) is not None:
            r = min(r, caps[key])
        a_ = acc[style]
        a_[0], a_[1], a_[2] = a_[0] + r * 20, a_[1] + 20, a_[2] + m / (m + mm) * 20
        heroes.append({**base, "score": round(r * 20, 1), "coverage": round(m / (m + mm), 2), "capped": caps.get(key) is not None})
        if r * 20 >= AGREE_PT:
            agree[style] += 1

    # 성장 거름망 — 매출·이익이 5%도 못 크거나, 최근 3년 적자·부채비율 200%↑
    rv = [v for _, v in HC.yr_vals(F["by"], "rev", 6)] or HC.last(F["rev"], 6)
    sg = cagr(rv[0], rv[-1], len(rv) - 1) if len(rv) >= 3 else None
    ni3 = [v for _, v in HC.yr_vals(F["by"], "ni", 3)] or HC.last(F["ni"], 3)
    growth_fail = bool((sg is not None and sg < HC.FISHER_GATE) or (F["eg"] is not None and F["eg"] < HC.FISHER_GATE)
                       or any(v <= 0 for v in ni3) or (F["dr"] and not F["fin_co"] and not F["us"] and F["dr"][-1] >= 200))
    steady = steady_growth(F["by"])
    fails = {"value": graham_fail, "growth": growth_fail}
    fail_why = {"value": "그레이엄 거름망 탈락(최근 10년 적자 연도·부채비율 200%↑)",
                "growth": "성장 거름망 탈락(매출·이익 성장 5% 미만 또는 최근 3년 적자·부채비율 200%↑)"}
    sty = {}
    for s_, (g_, mx, av) in acc.items():
        sc_ = round(g_ / mx * 100, 1) if mx else None
        cov = av / mx if mx else 0
        if sc_ is None or cov < 0.5:
            gr = {"key": "na", "label": "⚪ 데이터 부족", "desc": "판단에 필요한 재무 데이터가 절반 미만"}
        else:
            gk = next(g for g in GRADES if sc_ >= g[0])
            n_h = sum(1 for h in HEROES if h[5] == s_)
            if gk[1] == "core" and agree[s_] < AGREE_MIN and not fails[s_]:
                gk = GRADES[1]
                gr = {"key": gk[1], "label": gk[2], "desc": f"점수는 70↑지만 대가 {agree[s_]}/{n_h}명만 동의(14점↑) — 소수 의견에 기댄 고득점이라 위성으로"}
            elif fails[s_] and gk[1] in ("core", "sat"):
                gk = GRADES[2]
                gr = {"key": gk[1], "label": gk[2], "desc": fail_why[s_] + " — 점수와 상관없이 관찰까지만"}
            else:
                gr = {"key": gk[1], "label": gk[2], "desc": gk[3]}
        gr["label"] = gr["label"].replace("장기 ", STYLES[s_][1] + " ")
        sty[s_] = {"score": sc_, "coverage": round(cov, 2), "grade": gr, "fail": fails[s_], "agree": agree[s_],
                   "n_heroes": sum(1 for h in HEROES if h[5] == s_)}
    order = ["core", "sat", "watch", "no", "na"]
    v, g = sty["value"], sty["growth"]
    rank = lambda x: (order.index(x["grade"]["key"]), -(x["score"] or 0))
    best = "value" if rank(v) <= rank(g) else "growth"
    B = sty[best]
    both = v["grade"]["key"] in ("core", "sat") and g["grade"]["key"] in ("core", "sat")
    style = "both" if both else best if B["grade"]["key"] in ("core", "sat", "watch") else None
    gk = B["grade"]["key"]
    if gk == "na" and graham_fail and growth_fail:
        grade = {"key": "no", "label": GRADES[3][2], "desc": "가치·성장 거름망 모두 탈락 — " + GRADES[3][3]}
    elif gk in ("na", "no"):
        grade = dict(B["grade"])
    else:
        tag = "💎+🚀 " if both else STYLES[best][0] + " "
        nm = "가치·성장" if both else STYLES[best][1]
        lab = B["grade"]["label"].replace(STYLES[best][1] + " ", f"{nm} ")
        grade = {"key": gk, "label": lab, "desc": B["grade"]["desc"], "icon": tag.strip()}
    total = B["score"]
    note = None
    if (v["score"] or 0) >= 55 and (g["score"] or 0) < 40:
        note = "💎 가치형 — 싸고 튼튼하지만 성장은 약함 → 가치에 닿으면 매도(위성), 성장 기대로 오래 들고 가지 않기"
    elif (g["score"] or 0) >= 55 and (v["score"] or 0) < 40:
        note = "🚀 성장형 — 성장은 좋은데 가격·재무 쿠션이 얇음 → 성장이 꺾이면(분기 이익 둔화) 바로 점검, 비중은 작게"
    elif both:
        note = "💎+🚀 가치와 성장을 모두 갖춤 — 핵심 바구니 우선 후보"
    return {"total": total, "value": v, "growth": g, "style": style, "coverage": B["coverage"], "grade": grade, "note": note,
            "heroes": heroes, "src": F["src"], "steady": steady, "lynch_cat": cat, "lynch_sell": LYNCH_SELL.get(cat), "fin_co": F["fin_co"], "method": METHOD}


STEADY_N = 4                                          # 최근 4개 연도(3번의 변화)


def _steady(vals: list) -> bool | None:
    """꾸준히 증가 = 최근 4년 중 뒷걸음질 1번 이하 + 마지막 해가 첫해보다 큼 (3년치뿐이면 뒷걸음질 0번). 3년 미만이면 None(모름)"""
    v = [x for x in vals if x is not None][-STEADY_N:]
    if len(v) < 3:
        return None
    downs = sum(1 for a, b in zip(v, v[1:]) if b < a)
    return v[-1] > v[0] and downs <= (1 if len(v) >= 4 else 0)


def steady_growth(by: dict) -> dict:
    rv = [x for _, x in HC.yr_vals(by, "rev", STEADY_N)]
    ni = [x for _, x in HC.yr_vals(by, "ni", STEADY_N)]
    r, n = _steady(rv), _steady(ni)
    if n and ni and ni[-1] <= 0:                       # 적자 축소는 '증가'로 안 봄
        n = False
    ok = None if r is None or n is None else (r and n)
    return {"ok": ok, "rev": r, "ni": n, "rev_v": rv, "ni_v": ni}


METHOD = ("📖 = 책·주주서한에 나온 숫자 그대로 · ⚖️ = 원전에 숫자가 없어 정한 보조선(화면에 기준 공개). "
          "점수는 0점 선과 만점 선 사이를 직선으로, 한 대가 안의 항목은 같은 비중, 데이터 없는 항목은 반만 인정. "
          "가치 점수 = 버핏·그레이엄·멍거·애크먼·클라만 합(100) · 성장 점수 = 린치·피셔·드러켄밀러·템플턴·로 프라이스 합(100), "
          "등급은 높은 쪽 기준 · 핵심(70↑)은 그 쪽 대가 5명 중 3명 이상이 14점↑ 줘야 유지")


# ── 발굴 탭: 후보 묶음을 한꺼번에 채점 ─────────────────────
_DISK = os.path.join(os.path.expanduser(os.environ.get("CHART_CACHE_DIR", "~/.cache/bbchart")), "heroes")


def _disk(name: str, ttl: float, fn):
    """한 번 받은 건 디스크에 저장 → 기한 안이면 다시 안 받음 (코스피 전체 채점을 빠르게).
       자주 안 바뀌는 것만: 연간 재무 7일 · 분기 재무 3일 · 공시 목록 20시간. 시세·밸류(PER 등)는 매번 새로"""
    import json
    f = os.path.join(_DISK, name.replace("/", "_") + ".json")
    try:
        if time.time() - os.path.getmtime(f) < ttl:
            return json.load(open(f, encoding="utf-8"))
    except Exception:
        pass
    v = fn()
    try:
        os.makedirs(_DISK, exist_ok=True)
        json.dump(v, open(f + ".tmp", "w", encoding="utf-8"), ensure_ascii=False)
        os.replace(f + ".tmp", f)
    except Exception:
        pass
    return v


def light(code: str, name: str | None = None, corp_code: str | None = None) -> dict:
    """목록용 가벼운 데이터 — 밸류·종가·1년 일봉은 매번, 재무·공시는 디스크 저장본(기한 안이면)"""
    import stock_info as si
    prof = si.kr_profile(code)
    if prof.get("industry_code"):                     # 목록에서 바로 보이게 — 네이버 업종 이름(30일 저장)
        try:
            prof["industry"] = _disk(f"ind_{prof['industry_code']}", 30 * 86400,
                                     lambda: {"name": si.kr_industry_name(prof["industry_code"])}).get("name")
        except Exception:
            pass
    fa = _disk(f"fa_{code}", 7 * 86400, lambda: si.kr_finance(code, "annual"))
    fq, oh = {}, None
    try:                                              # 드러켄밀러 이익 변곡(분기 이익 증가율)용
        fq = _disk(f"fq_{code}", 3 * 86400, lambda: si.kr_finance(code, "quarter"))
    except Exception:
        pass
    try:                                              # 1년 주가(드러켄밀러 추세·낙폭 · 템플턴 비관 · 린치 과열 · 클라만 소외) — 최근 약 14개월만
        df = si.kr_ohlcv(code, 420)
        oh = {"d": [f"{x:%Y-%m-%d}" for x in df.index], "c": [float(c) for c in df["close"]]}
    except Exception:
        pass
    filings, fok = [], False
    try:
        if corp_code and (os.environ.get("DART_API_KEY") or os.environ.get("DART_KEY")):
            filings, fok = _disk(f"fl_{corp_code}", 20 * 3600, lambda: si.kr_filings(corp_code)), True
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
            "finance": {"annual": fa, "quarter": fq}, "filings": filings, "filings_ok": fok, "close": close or (oh["c"][-1] if oh else None),
            "dart": dart, "ohlc": oh}


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


def yf_pbr(tk, info: dict, sym: str):
    """해외 PBR = 시가총액 ÷ 자본총계 (둘 다 원화로 바꿔서).
       야후 priceToBook 은 ADR(TSM 등)에서 주가는 달러·장부가는 대만달러/원주 1주 기준이라 75배 같은 엉뚱한 값이 나와서 직접 계산.
       자본총계를 못 받으면 야후 값 그대로"""
    g = info.get
    mcap, ccy = g("marketCap"), g("currency")
    fccy = g("financialCurrency") or ccy

    def eq_get():
        for attr in ("quarterly_balance_sheet", "balance_sheet"):
            try:
                bs = getattr(tk, attr)
                if bs is None or bs.empty:
                    continue
                for row in ("Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest"):
                    if row in bs.index:
                        v = bs.loc[row].dropna()
                        if len(v):
                            return float(v.iloc[0])
            except Exception:
                pass
        return None
    try:
        eq = _disk(f"yeq_{sym}", 7 * 86400, eq_get)
        f1, f2 = _krw_per(ccy), _krw_per(fccy)
        if mcap and eq and f1 and f2:
            return mcap * f1 / (eq * f2)              # 자본잠식이면 마이너스 그대로
    except Exception:
        pass
    return g("priceToBook")


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
    prof = {"name": name or g("shortName") or sym, "per": g("trailingPE"), "fper": g("forwardPE"), "pbr": yf_pbr(tk, info, sym),
            "sector": si._ko_label(g("sector"), si.SECTOR_KO), "industry": si._ko_label(g("industry"), si.INDUSTRY_KO),
            "div_yield": dy, "roe": g("returnOnEquity"), "opm": g("operatingMargins"), "de": g("debtToEquity"),
            "target": g("targetMeanPrice"), "mcap_usd": mcap, "currency": ccy,
            "mcap_eok": mcap * fx / 1e8 if mcap and fx else None,
            "hi52": g("fiftyTwoWeekHigh"), "ret1y": g("52WeekChange"), "q_yoy": g("earningsQuarterlyGrowth")}
    try:                                              # (참고용) 자본수익률·이익수익률 — EBIT ≈ 영업이익률 × 매출, 투하자본 ≈ 자본 + 순차입
        ebit = (g("operatingMargins") or 0) * (g("totalRevenue") or 0) or None
        nd = (g("totalDebt") or 0) - (g("totalCash") or 0)
        eq = (g("bookValue") or 0) * (g("sharesOutstanding") or 0)
        ev = g("enterpriseValue") or ((mcap or 0) + nd)
        if ebit:
            prof["roc"] = ebit / (eq + nd) if eq + nd > 0 else None
            prof["ey"] = ebit / ev if ev and ev > 0 else None
    except Exception:
        pass
    fin = {}
    try:
        fin["annual"] = _disk(f"yfa_{sym}", 7 * 86400, lambda: si.yf_annual(tk))   # 4년치 (꾸준함 판단용) — 7일 저장
    except Exception:
        pass
    prof["summary_en"] = g("longBusinessSummary") or ""
    return {"us": True, "code": sym, "name": prof["name"], "profile": prof, "finance": fin, "filings": None, "close": price}


def about_line(d: dict) -> str | None:
    """목록에 보여 줄 '무슨 회사' 한 줄 — 해외: 야후 설명 첫 문장 한국어 번역 · 한국: 에프앤가이드 기업개요 첫 문장 (30일 저장)"""
    import stock_info as si
    P = d.get("profile") or {}
    def get():
        if d.get("us"):
            en = re.split(r"(?<=[a-z0-9)][.])\s+(?=[A-Z])", (P.get("summary_en") or "").strip())[0]
            if not en:
                return {"t": None}
            try:
                ko = si.ko_translate(en)
            except Exception:
                ko = None
            return {"t": ko or en}
        D = si.kr_desc(d["code"]) or {}
        ln = (D.get("lines") or [None])[0] or (D.get("text") or "").split(". ")[0]
        return {"t": ln or None}
    try:
        v = _disk(f"about_{d['code']}", 30 * 86400, get)
        t = (v or {}).get("t")
        return t[:140] if t else None
    except Exception:
        return None


def board_row(p: dict, market: str = "kr") -> dict:
    """종목 하나 채점 → 목록 한 줄 (실패하면 {"error": ...})"""
    try:
        d = light(p["code"], p.get("name"), p.get("corp_code")) if market == "kr" else light_global(p["code"], p.get("name"))
        s = score(d)
        P = d["profile"]
        return {"code": p["code"], "name": d["name"], "src": p.get("src", []), "held": p.get("held", False),
                "us": market != "kr", "ccy": (d["profile"] or {}).get("currency"),
                "total": s["total"], "grade": s["grade"], "note": s["note"], "lynch_cat": s["lynch_cat"],
                "value": s["value"]["score"], "growth": s["growth"]["score"], "style": s["style"],
                "vgrade": s["value"]["grade"]["key"], "ggrade": s["growth"]["grade"]["key"],
                "heroes": {h["key"]: h["score"] for h in s["heroes"]},
                "agree": {"value": s["value"]["agree"], "growth": s["growth"]["agree"]},
                "best": [c["text"] for h in s["heroes"] for c in h["checks"] if c["ok"] is True and not c.get("bonus")][:3],
                "worst": [c["text"] for h in s["heroes"] for c in h["checks"] if c["ok"] is False][:2],
                "steady": {k: s["steady"][k] for k in ("ok", "rev", "ni")},
                "per": P.get("per"), "pbr": P.get("pbr"), "yield": P.get("div_yield"), "mcap_eok": P.get("mcap_eok"),
                "industry": P.get("industry") or P.get("sector"), "about": about_line(d)}
    except Exception as e:
        return {"code": p["code"], "name": p.get("name") or p["code"], "error": f"{type(e).__name__}: {str(e)[:80]}"}


def aggregate(rows: list[dict], n_pool: int, market: str = "kr") -> dict:
    """채점된 줄들 → 순위·등급 집계 (board 와 DB 목록이 같이 씀)"""
    ok = [r for r in rows if r.get("total") is not None and r["grade"]["key"] != "na"]
    styles = {"value": sum(1 for r in ok if r["vgrade"] in ("core", "sat")), "growth": sum(1 for r in ok if r["ggrade"] in ("core", "sat")),
              "both": sum(1 for r in ok if r["style"] == "both")}
    ok.sort(key=lambda r: -r["total"])
    for i, r in enumerate(ok, 1):
        r["rank"] = i
    cnt = {}
    for r in ok:
        cnt[r["grade"]["key"]] = cnt.get(r["grade"]["key"], 0) + 1
    return {"items": ok, "failed": [r for r in rows if r not in ok], "n_pool": n_pool, "grades": cnt, "styles": styles, "market": market,
            "market_name": MARKET_NAME.get(market, market)}


def board(pool: list[dict], workers: int = 8, market: str = "kr", prog: dict | None = None) -> dict:
    """pool = [{code, name, corp_code, src:[...], held}] → 점수 순 목록 (market != kr 이면 해외 yfinance)"""
    def one(p):
        try:
            return board_row(p, market)
        finally:
            if prog is not None:
                prog["done"] = prog.get("done", 0) + 1
    if prog is not None:
        prog.update(done=0, total=len(pool))
    with ThreadPoolExecutor(workers) as ex:
        rows = list(ex.map(one, pool))
    return aggregate(rows, len(pool), market)


if __name__ == "__main__":
    import json
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import stock_info as si
    for q in sys.argv[1:] or ["005930"]:
        r = score(si.detail({"code": q, "us": not q.isdigit()}))
        print(q, "가치", r["value"]["score"], "성장", r["growth"]["score"], r["grade"]["label"], r["lynch_cat"], r["note"] or "")
        for h in r["heroes"]:
            print(f"  {h['icon']} {h['name']} {h['score']}/20")
            for c in h["checks"]:
                print(f"     {'✅' if c['ok'] else '❌' if c['ok'] is False else '·'} {c['text']}")
