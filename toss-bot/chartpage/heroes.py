"""
heroes.py — '내 주식 영웅 5인'의 기준으로 종목을 채점 (장기 투자 판단용)

  벤저민 그레이엄  🛡️ 안전마진   : 흑자 지속 · 부채 · 당좌비율 · 그레이엄 넘버(PER×PBR ≤ 22.5)
  워런 버핏       🏰 해자·ROE   : ROE 수준과 꾸준함 · 영업이익률 수준과 안정성
  필립 피셔       🌱 위대한 기업 : 매출 성장 · 이익 성장 · 이익률 개선 · 앞으로의 성장(컨센서스)
  피터 린치       🔎 성장 대비 가격: PEG · (성장률+배당)/PER · 적당한 크기·가격
  빌 애크먼       🎯 촉매·환원   : 자사주·배당 공시 · 희석 없음 · 재평가 여지 · 목표가 여력

각 20점, 합계 100점(데이터가 없는 항목은 빼고 환산). 등급:
  70↑ 장기 핵심 · 55↑ 장기 위성 · 40↑ 관찰 · 그 아래 장기 부적합
  그레이엄 거름망(적자 연도·과도한 부채)에 걸리면 점수와 상관없이 '관찰'까지만.

입력은 stock_info.kr_detail / us_detail 결과(dict) — 새로 데이터를 받지 않음.
목록(발굴 탭)용으로는 board()가 종목마다 가벼운 데이터(밸류·연간 재무·공시)만 받아 채점.

단독 테스트:  python3 heroes.py 005930 000660
"""
from __future__ import annotations

import math
import os
import sys
from concurrent.futures import ThreadPoolExecutor

HEROES = [
    ("graham", "벤저민 그레이엄", "🛡️", "안전마진", "잃지 않는 것이 먼저 — 흑자·낮은 부채·싼 가격"),
    ("buffett", "워런 버핏", "🏰", "해자·ROE", "훌륭한 기업을 적당한 가격에 — 높고 꾸준한 ROE"),
    ("fisher", "필립 피셔", "🌱", "위대한 기업", "몇 년 더 클 회사를 사서 오래 들고 간다"),
    ("lynch", "피터 린치", "🔎", "성장 대비 가격", "아는 회사를, 성장보다 싸게 (PEG ≤ 1)"),
    ("ackman", "빌 애크먼", "🎯", "촉매·환원", "시장이 가치를 알아볼 계기가 있는가"),
]

# 화면에 보여 줄 나의 원칙 (대시보드 홈·발굴 탭)
PRINCIPLES = {
    "mix": {"target_short": 0.10, "max_short": 0.20,
            "text": "장기 투자 9 : 단기 매매 1 — 단기는 많아도 2를 넘기지 않는다 (안정성 우선)"},
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


def _chk(pts, mx, text, ok=None):
    """ok=None → 데이터 없음(점수 계산에서 뺌)"""
    return {"pts": pts if ok is not None else 0, "max": mx, "ok": ok, "text": text}


# ── 5인 채점 ───────────────────────────────────────────
def score(d: dict) -> dict:
    """d = stock_info 상세(또는 board용 가벼운 dict). 반환: 영웅별 점수·체크·등급·린치 분류"""
    us = bool(d.get("us"))
    P = d.get("profile") or {}
    fin = d.get("finance") or {}
    filings = d.get("filings")
    has_filings = (not us) and filings is not None and d.get("filings_ok", True)

    sales, op, ni = _series(fin, "매출액"), _series(fin, "영업이익"), _series(fin, "당기순이익")
    opm, roe = _series(fin, "영업이익률"), _series(fin, "ROE")
    debt, quick, eps = _series(fin, "부채비율"), _series(fin, "당좌비율"), _series(fin, "EPS")
    eps_est = _series(fin, "EPS", est=True)
    if not roe and _ok(P.get("roe")):                 # 미국: yfinance ROE(소수)
        roe = [P["roe"] * 100]
    if not opm and _ok(P.get("opm")):
        opm = [P["opm"] * 100]
    if not debt and _ok(P.get("de")):
        debt = [P["de"]]                              # 미국: 부채/자본(%) — 국내 부채비율과 정의가 조금 다름
    per, pbr = P.get("per"), P.get("pbr")
    per = per if _ok(per) else None
    pbr = pbr if _ok(pbr) else None
    dy = P.get("div_yield") if _ok(P.get("div_yield")) else None
    mcap_eok = P.get("mcap_eok") if _ok(P.get("mcap_eok")) else (P["mcap_usd"] * 1400 / 1e8 if _ok(P.get("mcap_usd")) else None)
    roe_avg = sum(roe[-4:]) / len(roe[-4:]) if roe else None
    fin_co = bool(debt) and debt[-1] > 500 and (roe_avg or 0) > 0     # 은행·보험·증권: 부채비율이 본업 구조라 평가 제외
    years = max(len(sales), len(ni)) - 1

    H = {}
    # 🛡️ 그레이엄
    g = []
    if ni:
        neg = sum(1 for v in ni if v <= 0)
        g.append(_chk(6, 6, f"최근 {len(ni)}년 모두 흑자" if not neg else f"최근 {len(ni)}년 중 적자 {neg}번", ok=not neg))
        if neg:
            g[-1]["pts"] = 0
    else:
        g.append(_chk(0, 6, "순이익 데이터 없음"))
    if debt and not fin_co:
        dv = debt[-1]
        pts = 5 if dv < 100 else 2 if dv < 200 else 0
        g.append(_chk(pts, 5, f"{'부채/자본' if us else '부채비율'} {dv:.0f}% " + ("(낮음)" if dv < 100 else "(보통)" if dv < 200 else "(높음)"), ok=dv < 100))
    elif fin_co:
        g.append(_chk(0, 5, "금융업 — 부채비율 기준 제외"))
    else:
        g.append(_chk(0, 5, "부채 데이터 없음"))
    if quick and not fin_co:
        g.append(_chk(3 if quick[-1] >= 100 else 0, 3, f"당좌비율 {quick[-1]:.0f}% (100%↑ 목표 · 단기 지급 여력)", ok=quick[-1] >= 100))
    else:
        g.append(_chk(0, 3, "당좌비율 데이터 없음"))
    if per and pbr and per > 0:
        gn = per * pbr
        g.append(_chk(6 if gn <= 22.5 else 3 if gn <= 40 else 0, 6, f"그레이엄 넘버 PER×PBR = {gn:.1f} (22.5 이하면 싸다)", ok=gn <= 22.5))
    elif per is None and pbr:
        g.append(_chk(0, 6, "적자(PER 없음) — 그레이엄 넘버 계산 불가", ok=False))
    else:
        g.append(_chk(0, 6, "PER·PBR 데이터 없음"))
    H["graham"] = g
    graham_fail = (ni and any(v <= 0 for v in ni)) or (debt and not fin_co and debt[-1] >= 200)

    # 🏰 버핏
    b = []
    if roe:
        b.append(_chk(8 if roe_avg >= 15 else 4 if roe_avg >= 10 else 0, 8, f"ROE 평균 {roe_avg:.1f}% (최근 {len(roe[-4:])}년, 15%↑ 목표)", ok=roe_avg >= 15))
        mn = min(roe[-4:])
        if len(roe) >= 2:
            b.append(_chk(4 if mn >= 10 else 2 if mn >= 5 else 0, 4, f"가장 나빴던 해 ROE {mn:.1f}% (10%↑면 꾸준함)", ok=mn >= 10))
        else:
            b.append(_chk(0, 4, "ROE 1년치뿐 — 꾸준함 판단 불가"))
    else:
        b += [_chk(0, 8, "ROE 데이터 없음"), _chk(0, 4, "ROE 데이터 없음")]
    if opm and not fin_co:
        oa = sum(opm[-4:]) / len(opm[-4:])
        b.append(_chk(4 if oa >= 15 else 2 if oa >= 8 else 0, 4, f"영업이익률 평균 {oa:.1f}% (15%↑면 가격 결정력)", ok=oa >= 15))
        if len(opm) >= 3:
            rg = max(opm[-4:]) - min(opm[-4:])
            b.append(_chk(4 if rg <= 5 else 2 if rg <= 10 else 0, 4, f"영업이익률 변동 폭 {rg:.1f}%p (좁을수록 해자)", ok=rg <= 5))
        else:
            b.append(_chk(0, 4, "이익률 3년치 미만"))
    else:
        b += [_chk(0, 4, "영업이익률 데이터 없음" if not fin_co else "금융업 — 이익률 기준 제외"),
              _chk(0, 4, "영업이익률 데이터 없음" if not fin_co else "금융업 — 이익률 기준 제외")]
    H["buffett"] = b

    # 🌱 피셔
    f = []
    sg = _cagr(sales[0], sales[-1], len(sales) - 1) if len(sales) >= 3 else None
    if sg is not None:
        f.append(_chk(7 if sg >= 0.10 else 4 if sg >= 0.05 else 2 if sg > 0 else 0, 7,
                      f"매출 연평균 성장 {sg * 100:+.1f}% ({len(sales) - 1}년, 10%↑ 목표)", ok=sg >= 0.10))
    else:
        f.append(_chk(0, 7, "매출 성장 계산 불가(3년치 미만·적자)"))
    if len(op) >= 3:
        good = op[-1] > 0 and op[-1] > op[0]
        f.append(_chk(5 if good else 0, 5, f"영업이익 {op[0]:,.0f} → {op[-1]:,.0f}{'' if us else '억'}", ok=good))
    else:
        f.append(_chk(0, 5, "영업이익 3년치 미만"))
    if len(opm) >= 3 and not fin_co:
        imp = opm[-1] >= sum(opm[:-1]) / len(opm[:-1])
        f.append(_chk(4 if imp else 0, 4, f"최근 영업이익률 {opm[-1]:.1f}% vs 이전 평균 {sum(opm[:-1]) / len(opm[:-1]):.1f}%", ok=imp))
    else:
        f.append(_chk(0, 4, "이익률 개선 판단 불가"))
    if eps_est and eps and eps[-1] > 0:
        up = eps_est[0] / eps[-1] - 1
        f.append(_chk(4 if up >= 0.05 else 2 if up >= 0 else 0, 4, f"증권사 추정 다음 해 EPS {up * 100:+.0f}%", ok=up >= 0.05))
    else:
        f.append(_chk(0, 4, "EPS 추정치 없음"))
    H["fisher"] = f

    # 🔎 린치
    l = []
    gr = None
    if len(eps) >= 3 and eps[0] > 0 and eps[-1] > 0:
        gr = _cagr(eps[0], eps[-1], len(eps) - 1)
    elif eps_est and eps and eps[-1] > 0:
        gr = eps_est[0] / eps[-1] - 1
    elif len(ni) >= 3 and ni[0] > 0 and ni[-1] > 0:
        gr = _cagr(ni[0], ni[-1], len(ni) - 1)
    if per and per > 0 and gr is not None:
        if gr > 0:
            peg = per / (gr * 100)
            l.append(_chk(8 if peg <= 1 else 4 if peg <= 1.5 else 0, 8, f"PEG {peg:.2f} = PER {per:.1f} ÷ 이익성장 {gr * 100:.1f}% (1 이하면 싸다)", ok=peg <= 1))
        else:
            l.append(_chk(0, 8, f"이익 성장 {gr * 100:+.1f}% — PEG 의미 없음", ok=False))
        lr = (max(gr, 0) * 100 + (dy or 0)) / per
        l.append(_chk(6 if lr >= 2 else 3 if lr >= 1.5 else 0, 6, f"(성장률+배당수익률)/PER = {lr:.2f} (2 이상이면 매력, 1 미만 비쌈)", ok=lr >= 2))
    else:
        loss = bool(ni) and ni[-1] <= 0
        l += [_chk(0, 8, "적자 — PEG 계산 불가", ok=False) if loss else _chk(0, 8, "PER 또는 이익 성장 데이터 없음"),
              _chk(0, 6, "적자 — 린치 비율 계산 불가", ok=False) if loss else _chk(0, 6, "린치 비율 계산 불가")]
    if per and per > 0:
        l.append(_chk(3 if per <= 20 else 1 if per <= 30 else 0, 3, f"PER {per:.1f}배 (20 이하 적당)", ok=per <= 20))
    else:
        l.append(_chk(0, 3, "PER 없음"))
    if mcap_eok:
        small = mcap_eok < 100000
        l.append(_chk(3 if small else 1, 3, f"시가총액 {mcap_eok / 10000:.1f}조 " + ("(린치가 좋아한 중소형 — 더 클 여지)" if small else "(대형 — 큰 폭 상승은 어려움)"), ok=small))
    else:
        l.append(_chk(0, 3, "시가총액 데이터 없음"))
    H["lynch"] = l

    # 🎯 애크먼
    a = []
    if has_filings:
        tags = [x.get("tag") for x in filings]
        ret = [x for x in filings if x.get("tag") in ("자사주", "배당")]
        a.append(_chk(6 if ret else 0, 6, f"최근 120일 주주환원 공시 {len(ret)}건" + (f" ({ret[0]['title'][:24]})" if ret else ""), ok=bool(ret)))
        dil = sum(1 for t in tags if t == "증자·CB")
        a.append(_chk(4 if not dil else 0, 4, "최근 120일 증자·CB(희석) 공시 없음" if not dil else f"증자·CB 공시 {dil}건 — 희석 위험", ok=not dil))
    else:
        reason = "해외 종목 — DART 공시 기준 제외" if us else "공시 데이터 없음(DART 키 확인)"
        a += [_chk(0, 6, reason), _chk(0, 4, reason)]
    if pbr and roe_avg is not None:
        if pbr < 1 and roe_avg >= 8:
            a.append(_chk(5, 5, f"PBR {pbr:.2f} < 1인데 ROE {roe_avg:.0f}% — 재평가 여지 큼", ok=True))
        elif pbr < 1.5 and roe_avg >= 12:
            a.append(_chk(3, 5, f"PBR {pbr:.2f} · ROE {roe_avg:.0f}% — 재평가 여지 있음", ok=True))
        else:
            a.append(_chk(0, 5, f"PBR {pbr:.2f} · ROE {roe_avg:.0f}% — 할인 해소형 아님", ok=False))
    else:
        a.append(_chk(0, 5, "PBR·ROE 데이터 없음"))
    if dy is not None:
        a.append(_chk(2 if dy >= 2 else 0, 2, f"배당수익률 {dy:.2f}% (2%↑)", ok=dy >= 2))
    else:
        a.append(_chk(0, 2, "배당 데이터 없음"))
    tgt, close = P.get("target"), (d.get("tech") or {}).get("close") or d.get("close")
    if _ok(tgt) and _ok(close) and close:
        upx = tgt / close - 1
        a.append(_chk(3 if upx >= 0.2 else 1 if upx >= 0.05 else 0, 3, f"증권사 목표가 여력 {upx * 100:+.0f}%", ok=upx >= 0.2))
    else:
        a.append(_chk(0, 3, "목표가 없음"))
    H["ackman"] = a

    # 합계
    heroes, got, mx_all = [], 0, 0
    for key, name, icon, theme, motto in HEROES:
        cs = H[key]
        ev = [c for c in cs if c["ok"] is not None]
        p, m = sum(c["pts"] for c in ev), sum(c["max"] for c in ev)
        got, mx_all = got + p, mx_all + m
        heroes.append({"key": key, "name": name, "icon": icon, "theme": theme, "motto": motto,
                       "score": round(p / m * 20, 1) if m else None, "coverage": m / 20, "checks": cs})
    total = round(got / mx_all * 100, 1) if mx_all else None
    coverage = mx_all / 100
    if graham_fail and (total is None or coverage < 0.5):
        grade = {"key": "no", "label": GRADES[3][2], "desc": "적자 연도·부채 과다(그레이엄 거름망 탈락) — " + GRADES[3][3]}
    elif total is None or coverage < 0.5:
        grade = {"key": "na", "label": "⚪ 데이터 부족", "desc": "판단에 필요한 재무 데이터가 절반 미만"}
    else:
        gk = next(g for g in GRADES if total >= g[0])
        if graham_fail and gk[1] in ("core", "sat"):
            gk = GRADES[2]
            grade = {"key": gk[1], "label": gk[2], "desc": "그레이엄 거름망 탈락(적자 연도·부채 과다) — 점수와 상관없이 관찰까지만"}
        else:
            grade = {"key": gk[1], "label": gk[2], "desc": gk[3]}
    # 좋은 회사인데 비싼 경우
    q = sum(h["score"] or 0 for h in heroes if h["key"] in ("buffett", "fisher"))
    pr = sum(h["score"] or 0 for h in heroes if h["key"] in ("graham", "lynch"))
    note = None
    if q >= 28 and pr < 16:
        note = "🏰 품질(버핏·피셔)은 좋은데 가격(그레이엄·린치)이 비쌈 → 좋은 회사 목록에 두고 가격이 내려오길 기다리기"
    elif pr >= 28 and q < 16:
        note = "🛡️ 싸지만 품질이 약함 → 핵심이 아닌 위성(자산주)으로만, 가치에 닿으면 매도"
    cat = lynch_category(sales, op, ni, pbr, dy, mcap_eok, roe_avg)
    return {"total": total, "coverage": round(coverage, 2), "grade": grade, "note": note, "heroes": heroes,
            "lynch_cat": cat, "lynch_sell": LYNCH_SELL.get(cat), "fin_co": fin_co}


def lynch_category(sales, op, ni, pbr, dy, mcap_eok, roe_avg) -> str:
    """피터 린치의 6가지 분류(+중간) — 연간 재무로 기계적으로 추정"""
    sg = _cagr(sales[0], sales[-1], len(sales) - 1) if len(sales) >= 3 else None
    if len(ni) >= 2 and any(v <= 0 for v in ni[:-1]) and ni[-1] > 0:
        return "회생주"
    if pbr is not None and pbr < 0.6 and (roe_avg is None or roe_avg < 8):
        return "자산주"
    if len(op) >= 3:
        pos = [v for v in op if v is not None]
        m = sum(pos) / len(pos) if pos else 0
        if m > 0:
            sd = (sum((v - m) ** 2 for v in pos) / len(pos)) ** 0.5
            if sd / m > 0.6 or min(pos) <= 0:
                return "경기순환주"
    if sg is not None and sg >= 0.15:
        return "고성장주"
    if mcap_eok and mcap_eok >= 100000 and sg is not None and sg >= 0.03:
        return "대형우량주"
    if sg is not None and sg < 0.04 and (dy or 0) >= 2.5:
        return "저성장주"
    return "보통주(중간)"


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
    close = None
    try:                                              # 종가: 네이버 integration 에는 없어서 연간 재무 대신 목표가 여력용으로만 씀
        close = si.num((si._get(f"{si.NAVER}/{code}/basic").json() or {}).get("closePrice"))
    except Exception:
        pass
    return {"us": False, "code": code, "name": prof.get("name") or name or code, "profile": prof,
            "finance": {"annual": fa}, "filings": filings, "filings_ok": fok, "close": close}


def board(pool: list[dict], workers: int = 8) -> dict:
    """pool = [{code, name, corp_code, src:[...], held}] → 점수 순 목록"""
    def one(p):
        try:
            d = light(p["code"], p.get("name"), p.get("corp_code"))
            s = score(d)
            P = d["profile"]
            return {"code": p["code"], "name": d["name"], "src": p.get("src", []), "held": p.get("held", False),
                    "total": s["total"], "grade": s["grade"], "note": s["note"], "lynch_cat": s["lynch_cat"],
                    "heroes": {h["key"]: h["score"] for h in s["heroes"]},
                    "best": [c["text"] for h in s["heroes"] for c in h["checks"] if c["ok"]][:3],
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
    return {"items": ok, "failed": [r for r in rows if r not in ok], "n_pool": len(pool), "grades": cnt}


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
