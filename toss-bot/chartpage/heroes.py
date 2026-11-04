"""
heroes.py — '내 투자 대가 5인'의 기준으로 종목을 채점 (장기 투자 판단용)

  벤저민 그레이엄  🛡️ 안전마진   : 흑자 지속 · 부채 · 당좌비율 · 그레이엄 넘버(PER×PBR ≤ 22.5)
  워런 버핏       🏰 해자·ROE   : ROE 수준과 꾸준함 · 영업이익률 수준과 안정성
  필립 피셔       🌱 위대한 기업 : 매출 성장 · 이익 성장 · 이익률 개선 · 앞으로의 성장(컨센서스)
  피터 린치       🔎 성장 대비 가격: PEG · (성장률+배당)/PER · 적당한 크기·가격
  빌 애크먼       🎯 촉매·환원   : 자사주·배당 공시 · 희석 없음 · 재평가 여지 · 목표가 여력

각 20점, 합계를 100점으로 환산(데이터가 없는 항목은 빼고 환산). 등급:
  70↑ 장기 핵심 · 55↑ 장기 위성 · 40↑ 관찰 · 그 아래 장기 부적합
  그레이엄 거름망(적자 연도·과도한 부채)에 걸리면 점수와 상관없이 '관찰'까지만.

입력은 stock_info.kr_detail / us_detail 결과(dict) — 새로 데이터를 받지 않음.
목록(발굴 탭)용으로는 board()가 종목마다 가벼운 데이터(밸류·연간 재무·공시)만 받아 채점.

단독 테스트:  python3 heroes.py 005930 000660
"""
from __future__ import annotations

import math
import os
import re
import time
import sys
from concurrent.futures import ThreadPoolExecutor

HEROES = [   # (키, 이름, 아이콘, 주제, 한 줄 원칙 — 출처)
    ("graham", "벤저민 그레이엄", "🛡️", "안전마진", "『현명한 투자자』 방어적 투자자 7기준 — 규모·재무·10년 흑자·배당 이력·이익 성장·PER 15·PBR 1.5"),
    ("buffett", "워런 버핏", "🏰", "해자·ROE", "버크셔 인수 기준 — 꾸준한 수익력, 빚 없이 높은 ROE, 단순한 사업, 그리고 적당한 가격"),
    ("fisher", "필립 피셔", "🌱", "위대한 기업", "『위대한 기업에 투자하라』 15가지 — 매출을 키울 힘, 높고 나아지는 이익률, 희석 없는 성장"),
    ("lynch", "피터 린치", "🔎", "성장 대비 가격", "『전설로 떠나는 월가의 영웅』 — PEG·(성장+배당)/PER·빚·재고·순현금, 아는 회사를"),
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


def _facts(d: dict) -> dict:
    """채점용 숫자 모음 — 한국은 DART 10년(있으면) · 아니면 네이버/야후 연간 4년. 리스트는 오래된 → 최신"""
    us = bool(d.get("us"))
    P = d.get("profile") or {}
    fin = d.get("finance") or {}
    ok = lambda v: v if _ok(v) else None
    F = {"us": us, "per": ok(P.get("per")), "pbr": ok(P.get("pbr")), "dy": ok(P.get("div_yield")),
         "mcap_eok": ok(P.get("mcap_eok")) or (P["mcap_usd"] * 1400 / 1e8 if _ok(P.get("mcap_usd")) else None),
         "close": ok((d.get("tech") or {}).get("close")) or ok(d.get("close")), "target": ok(P.get("target")),
         "eps_est": _series(fin, "EPS", est=True), "src": "naver"}
    dart = d.get("dart") or {}
    K = {"rev": "매출액", "op": "영업이익", "ni": "당기순이익", "nio": "지배순이익", "eps": "EPS", "dps": "DPS", "eq": "자본총계",
         "eqo": "지배자본", "liab": "부채총계", "ca": "유동자산", "cl": "유동부채", "inv": "재고자산", "ncl": "비유동부채", "cash": "현금성자산",
         "netcash": "순현금", "ocf": "영업CF", "fcf": "FCF", "roe": "ROE", "opm": "영업이익률", "dr": "부채비율", "cr": "유동비율"}
    if dart.get("labels") and dart.get("key") and not dart.get("error"):
        labs = dart["labels"]
        idx = sorted([i for i, l in enumerate(labs) if l.isdigit()], key=lambda i: labs[i])
        for k, nm in K.items():
            v = dart["key"].get(nm) or [None] * len(labs)
            F[k] = [v[i] for i in idx]
        F["years"], F["src"] = [labs[i] for i in idx], "dart"
    else:
        R = lambda nm: _series(fin, nm)
        F.update({"rev": R("매출액"), "op": R("영업이익"), "ni": R("당기순이익"), "eps": R("EPS"), "dps": R("주당배당금"),
                  "roe": R("ROE"), "opm": R("영업이익률"), "dr": R("부채비율"), "cr": R("유동비율"), "nio": [], "eq": [], "eqo": [],
                  "liab": [], "ca": [], "cl": [], "inv": [], "ncl": [], "cash": [], "netcash": [], "ocf": [], "fcf": []})
        if not F["roe"] and _ok(P.get("roe")):
            F["roe"] = [P["roe"] * 100]
        if not F["opm"] and _ok(P.get("opm")):
            F["opm"] = [P["opm"] * 100]
        if not F["dr"] and _ok(P.get("de")):
            F["dr"] = [P["de"]]
    # 지배주주 순이익 / EPS → 주식 수(희석 판단)
    nio = F.get("nio") or []
    F["shares"] = [(n * 1e8 / e) if (n and e and e > 0) else None for n, e in zip(nio, F["eps"])] if nio else []
    dr = _last(F["dr"], 1)
    ra = _last(F["roe"], 4)
    F["fin_co"] = bool(dr) and dr[0] > 500 and bool(ra) and sum(ra) / len(ra) > 0
    for k in ("rev", "op", "ni", "eps", "roe", "opm", "dr"):
        F[k] = [v for v in F[k] if v is not None] if k in ("rev", "op", "ni", "eps", "roe", "opm", "dr") else F[k]
    return F


# ── 5인 채점 ───────────────────────────────────────────
def score(d: dict) -> dict:
    """d = stock_info 상세(또는 board용 가벼운 dict). 반환: 대가별 점수·체크·등급·린치 분류"""
    us = bool(d.get("us"))
    P = d.get("profile") or {}
    fin = d.get("finance") or {}
    filings = d.get("filings")
    has_filings = (not us) and filings is not None and d.get("filings_ok", True)

    F = _facts(d)
    sales, op, ni, eps = F["rev"], F["op"], F["ni"], F["eps"]
    opm, roe, debt = F["opm"], F["roe"], F["dr"]
    per, pbr, dy, mcap_eok, close = F["per"], F["pbr"], F["dy"], F["mcap_eok"], F["close"]
    roe_avg = sum(_last(roe, 10)) / len(_last(roe, 10)) if _last(roe, 10) else None
    fin_co = F["fin_co"]
    H, T = {}, {}
    N = len(_last(ni, 10))

    # 🛡️ 그레이엄 — 『현명한 투자자』 14장 방어적 투자자 7기준 (+15장 넷넷)
    g = []
    g.append(_chk(2 if (mcap_eok or 0) >= 2000 else 0, 2, f"① 충분한 규모: 시가총액 {(mcap_eok or 0) / 10000:.1f}조 (2,000억↑)", ok=(mcap_eok or 0) >= 2000)
             if mcap_eok else _chk(0, 2, "① 규모: 시가총액 데이터 없음"))
    cr, wc_ok = _lastv(F["cr"]), None
    if fin_co:
        g.append(_chk(0, 4, "② 재무 상태: 금융업 — 유동비율 기준 제외(그레이엄도 공익·금융은 따로 봄)", na=True))
    elif cr is not None:
        ca, cl, ncl = _lastv(F["ca"]), _lastv(F["cl"]), _lastv(F["ncl"])
        wc_ok = (ca is not None and cl is not None and ncl is not None and ncl <= ca - cl)
        pts = (2 if cr >= 200 else 1 if cr >= 150 else 0) + (2 if wc_ok else 0)
        g.append(_chk(pts, 4, f"② 재무 상태: 유동비율 {cr:.0f}% (200%↑) · 장기부채 {'≤' if wc_ok else '>'} 순유동자산", ok=cr >= 200 and wc_ok))
    else:
        g.append(_chk(0, 4, "② 재무 상태: 유동비율 데이터 없음"))
    if N:
        neg = sum(1 for v in _last(ni, 10) if v <= 0)
        pts = (4 if N >= 8 else 3 if N >= 5 else 2) if not neg else (1 if neg == 1 else 0)
        g.append(_chk(pts, 4, f"③ 이익 안정: 최근 {N}년 " + ("모두 흑자" if not neg else f"중 적자 {neg}번") + " (10년 무적자 목표)", ok=not neg))
    else:
        g.append(_chk(0, 4, "③ 이익 안정: 순이익 데이터 없음"))
    dps = _last(F["dps"], 12)
    if dps:
        run = 0
        for v in reversed(dps):
            if v and v > 0:
                run += 1
            else:
                break
        g.append(_chk(3 if run >= 10 else 2 if run >= 5 else 1 if run >= 1 else 0, 3, f"④ 배당 이력: {run}년 연속 배당 (원전 20년 — 데이터는 최대 12년)", ok=run >= 5))
    elif dy is not None:
        g.append(_chk(1 if dy > 0 else 0, 3, f"④ 배당 이력: 현재 배당 {'있음' if dy > 0 else '없음'} (연속 연수 데이터 없음)", ok=None if dy > 0 else False))
    else:
        g.append(_chk(0, 3, "④ 배당 이력: 데이터 없음"))
    e = _last(eps, 10)
    if len(e) >= 6:
        a0, a1 = sum(e[:3]) / 3, sum(e[-3:]) / 3
        gr = a1 / a0 - 1 if a0 > 0 else None
        g.append(_chk(2 if gr is not None and gr >= 1 / 3 else 0, 2, f"⑤ 이익 성장: 3년 평균 EPS {a0:,.0f} → {a1:,.0f} ({'계산 불가' if gr is None else f'{gr * 100:+.0f}%'}, +33%↑)", ok=gr is not None and gr >= 1 / 3))
    else:
        g.append(_chk(0, 2, "⑤ 이익 성장: EPS 6년치 미만"))
    e3 = _last(eps, 3)
    if close and len(e3) == 3 and sum(e3) > 0:
        pe3 = close / (sum(e3) / 3)
        g.append(_chk(3 if pe3 <= 15 else 1 if pe3 <= 20 else 0, 3, f"⑥ 적당한 PER: 주가 / 3년 평균 EPS = {pe3:.1f}배 (15배↓)", ok=pe3 <= 15))
    elif per:
        g.append(_chk(3 if per <= 15 else 1 if per <= 20 else 0, 3, f"⑥ 적당한 PER: {per:.1f}배 (15배↓ · 3년 평균 EPS 없어 현재 PER로)", ok=per <= 15))
    else:
        g.append(_chk(0, 3, "⑥ PER: 적자이거나 데이터 없음", ok=False if pbr else None))
    if pbr and per and per > 0:
        gn = per * pbr
        ok = pbr <= 1.5 or gn <= 22.5
        g.append(_chk(2 if ok else 0, 2, f"⑦ 적당한 PBR: {pbr:.2f}배 · PER×PBR {gn:.1f} (PBR 1.5↓ 또는 22.5↓)", ok=ok))
    elif pbr:
        g.append(_chk(2 if pbr <= 1.5 else 0, 2, f"⑦ 적당한 PBR: {pbr:.2f}배 (1.5↓)", ok=pbr <= 1.5))
    else:
        g.append(_chk(0, 2, "⑦ PBR 데이터 없음"))
    ca, li = _lastv(F["ca"]), _lastv(F["liab"])
    if mcap_eok and ca is not None and li is not None and not fin_co and ca - li > 0 and mcap_eok < (ca - li) * 2 / 3:
        g.append(_chk(0, 0, f"💎 넷넷(15장): 시총 {mcap_eok:,.0f}억 < 순유동자산(유동자산−부채) {ca - li:,.0f}억의 2/3 — 그레이엄의 '헐값' 종목", ok=True))
    H["graham"] = g
    T["graham"] = ["시장(미스터 마켓)의 기분에 휩쓸리지 않고 가격이 가치보다 충분히 쌀 때만 사는가(안전마진)",
                   "한 종목에 몰지 않고 10~30종목으로 나눴는가(방어적 투자자)"]
    graham_fail = bool(N and any(v <= 0 for v in _last(ni, 10))) or bool(debt and not fin_co and debt[-1] >= 200)

    # 🏰 버핏 — 버크셔 인수 기준(연차보고서) · 주주서한의 '높은 ROE·적은 부채·현금 창출·적당한 가격'
    b = []
    nn = _last(ni, 10)
    if len(nn) >= 3:
        pos = all(v > 0 for v in nn)
        drops = sum(1 for a_, b_ in zip(nn, nn[1:]) if a_ > 0 and b_ < a_ * 0.5)
        pts = 4 if pos and not drops else 2 if pos else 0
        b.append(_chk(pts, 4, f"꾸준한 수익력: 최근 {len(nn)}년 {'모두 흑자' if pos else '적자 있음'}" + (f" · 이익 반토막 {drops}번" if drops else " · 급감 없음") + " (턴어라운드 X)", ok=pos and not drops))
    else:
        b.append(_chk(0, 4, "꾸준한 수익력: 3년치 미만"))
    rr = _last(roe, 10)
    if rr:
        b.append(_chk(5 if roe_avg >= 15 else 3 if roe_avg >= 12 else 1 if roe_avg >= 8 else 0, 5, f"높은 ROE: 평균 {roe_avg:.1f}% (최근 {len(rr)}년, 15%↑)", ok=roe_avg >= 15))
        if len(rr) >= 3:
            mn = min(rr)
            b.append(_chk(3 if mn >= 12 else 1.5 if mn >= 7 else 0, 3, f"꾸준한 ROE: 가장 나빴던 해 {mn:.1f}% (12%↑)", ok=mn >= 12))
        else:
            b.append(_chk(0, 3, f"꾸준한 ROE: {len(rr)}년치뿐 — 판단 불가(반만 인정)"))
    else:
        b += [_chk(0, 5, "ROE 데이터 없음"), _chk(0, 3, "ROE 데이터 없음")]
    if fin_co:
        b.append(_chk(0, 3, "적은 부채: 금융업 — 기준 제외", na=True))
    elif debt:
        nc = _lastv(F["netcash"])
        dv = debt[-1]
        pts = 3 if dv <= 50 or (nc is not None and nc > 0) else 2 if dv <= 100 else 1 if dv <= 150 else 0
        b.append(_chk(pts, 3, f"적은 부채: 부채비율 {dv:.0f}%" + (f" · 순현금 {nc:,.0f}{'' if F['us'] else '억'}" if nc is not None and nc > 0 else "") + " (빚 없이 높은 ROE)", ok=pts >= 2))
    else:
        b.append(_chk(0, 3, "적은 부채: 데이터 없음"))
    fc, nq = _last(F["fcf"], 5), _last(ni, 5)
    if len(fc) >= 3 and len(nq) >= 3 and sum(nq[-len(fc):]) > 0:
        conv = sum(fc) / sum(nq[-len(fc):])
        b.append(_chk(2 if conv >= 0.8 else 1 if conv >= 0.5 else 0, 2, f"주주 이익(현금 전환): {len(fc)}년 FCF/순이익 {conv * 100:.0f}% (80%↑면 이익이 진짜 현금)", ok=conv >= 0.8))
    else:
        b.append(_chk(0, 2, "주주 이익(FCF): 데이터 없음"))
    if per is not None and per > 0:
        b.append(_chk(3 if per <= 15 else 1.5 if per <= 22 else 0, 3, f"적당한 가격: PER {per:.1f}배 = 이익수익률 {100 / per:.1f}% (15배↓ 적당 · 22배↑ 비쌈)", ok=per <= 22))
    elif per is not None:
        b.append(_chk(0, 3, "적당한 가격: 적자 — 버핏은 사지 않음", ok=False))
    else:
        b.append(_chk(0, 3, "가격: PER 없음"))
    H["buffett"] = b
    T["buffett"] = ["사업이 단순해서 10년 뒤 모습을 그릴 수 있는가(능력의 범위)", "가격을 올려도 고객이 떠나지 않는 해자가 있는가",
                    "경영진이 정직하고 남는 돈을 주주에게 이롭게 쓰는가(자본 배분)", "10년 동안 주식시장이 문을 닫아도 들고 있을 수 있는가"]

    # 🌱 피셔 — 『위대한 기업에 투자하라』 15가지 포인트 중 숫자로 볼 수 있는 것
    f = []
    sv = _last(sales, 6)
    sg = _cagr(sv[0], sv[-1], len(sv) - 1) if len(sv) >= 3 else None
    if sg is not None:
        f.append(_chk(5 if sg >= 0.10 else 3 if sg >= 0.05 else 1 if sg > 0 else 0, 5, f"①② 매출 성장: 연평균 {sg * 100:+.1f}% ({len(sv) - 1}년, 10%↑)", ok=sg >= 0.10))
    else:
        f.append(_chk(0, 5, "①② 매출 성장: 3년치 미만"))
    ov = _last(op, 6)
    og = _cagr(ov[0], ov[-1], len(ov) - 1) if len(ov) >= 3 else None
    if len(ov) >= 3:
        pts = 4 if (og or 0) >= 0.12 else 2 if (og or 0) >= 0.05 else 0.5 if ov[-1] > ov[0] > 0 else 0
        f.append(_chk(pts, 4, f"이익 성장: 영업이익 {ov[0]:,.0f} → {ov[-1]:,.0f}" + (f" (연 {og * 100:+.0f}%, 12%↑)" if og is not None else " (적자 구간 포함)"), ok=(og or 0) >= 0.12))
    else:
        f.append(_chk(0, 4, "이익 성장: 3년치 미만"))
    om = _last(opm, 6)
    if fin_co:
        f += [_chk(0, 3, "⑤ 이익률: 금융업 — 제외", na=True), _chk(0, 3, "⑥ 이익률 개선: 금융업 — 제외", na=True)]
    elif om:
        oa = sum(om) / len(om)
        f.append(_chk(3 if oa >= 15 else 1.5 if oa >= 8 else 0, 3, f"⑤ 높은 이익률: 영업이익률 평균 {oa:.1f}% (15%↑)", ok=oa >= 15))
        if len(om) >= 3:
            prev = sum(om[:-2]) / len(om[:-2]) if len(om) > 2 else om[0]
            recent = sum(om[-2:]) / 2
            imp = recent >= prev + 0.5
            f.append(_chk(3 if imp else 1.5 if recent >= prev - 1 else 0, 3, f"⑥ 이익률 개선: 최근 2년 {recent:.1f}% vs 이전 {prev:.1f}%", ok=imp))
        else:
            f.append(_chk(0, 3, "⑥ 이익률 개선: 3년치 미만"))
    else:
        f += [_chk(0, 3, "⑤ 이익률 데이터 없음"), _chk(0, 3, "⑥ 이익률 데이터 없음")]
    sh = [x for x in _last(F["shares"], 6) if x]
    if len(sh) >= 3:
        dil = sh[-1] / sh[0] - 1
        f.append(_chk(3 if dil <= 0.02 else 1 if dil <= 0.10 else 0, 3, f"⑬ 희석 없음: 주식 수 {dil * 100:+.0f}% ({len(sh)}년, 2%↓)", ok=dil <= 0.02))
    else:
        f.append(_chk(0, 3, "⑬ 희석: 주식 수 데이터 없음"))
    ee = F["eps_est"]
    if ee and eps and eps[-1] and eps[-1] > 0:
        up = ee[0] / eps[-1] - 1
        f.append(_chk(2 if up >= 0.05 else 1 if up >= 0 else 0, 2, f"①앞으로의 성장: 증권사 추정 다음 해 EPS {up * 100:+.0f}%", ok=up >= 0.05))
    else:
        f.append(_chk(0, 2, "앞으로의 성장: EPS 추정치 없음"))
    H["fisher"] = f
    T["fisher"] = ["③ 매출을 키울 연구개발·신제품이 계속 나오는가", "④ 영업 조직이 강한가", "⑦⑧ 노사·임원 관계가 좋은가",
                   "⑪ 경쟁사보다 뛰어난 점이 분명한가", "⑫ 경영진이 단기 실적보다 장기를 보는가", "⑭ 나쁜 소식도 솔직하게 말하는가", "⑮ 경영진이 정직한가 (주변 취재 '사실 수집')"]

    # 🔎 린치 — 『전설로 떠나는 월가의 영웅』 PEG · 배당 조정 · 재무 · 재고 · 순현금 · 자사주 · 크기
    l = []
    en = [x for x in _last(eps, 4) if x is not None]
    ng = _cagr(en[0], en[-1], len(en) - 1) if len(en) >= 3 and en[0] > 0 and en[-1] > 0 else None
    if ng is None:
        nv = _last(ni, 4)
        ng = _cagr(nv[0], nv[-1], len(nv) - 1) if len(nv) >= 3 else None
    if per and per > 0 and ng and ng > 0:
        peg = per / (ng * 100)
        l.append(_chk(5 if peg <= 0.5 else 3.5 if peg <= 1 else 1.5 if peg <= 1.5 else 0, 5, f"PEG {peg:.2f} = PER {per:.1f} ÷ 이익성장 {ng * 100:.0f}% (1↓ 싸다 · 0.5↓ 아주 싸다)", ok=peg <= 1))
        ad = (ng * 100 + (dy or 0)) / per
        l.append(_chk(3 if ad >= 2 else 2 if ad >= 1.5 else 1 if ad >= 1 else 0, 3, f"(성장률+배당수익률)/PER = {ad:.2f} (2↑ 매력 · 1↓ 비쌈)", ok=ad >= 1.5))
        gtxt = "적당(15~30%)" if 0.15 <= ng <= 0.30 else "너무 빠름 — 오래 못 감" if ng > 0.5 else "빠른 편" if ng > 0.30 else "느린 편"
        l.append(_chk(2 if 0.15 <= ng <= 0.30 else 1 if 0.10 <= ng <= 0.50 else 0, 2, f"성장 속도: 연 {ng * 100:.0f}% {gtxt}", ok=0.15 <= ng <= 0.30))
    elif per and per > 0:
        l += [_chk(0, 5, f"PEG: 이익이 줄어 계산 불가 (PER {per:.1f})", ok=False), _chk(0, 3, "(성장+배당)/PER: 성장 없음", ok=(dy or 0) / per >= 1 if dy else False),
              _chk(0, 2, "성장 속도: 감소", ok=False)]
    else:
        l += [_chk(0, 5, "PEG: 적자·데이터 없음", ok=False if per is not None else None), _chk(0, 3, "(성장+배당)/PER 계산 불가"), _chk(0, 2, "성장 속도 데이터 없음")]
    if fin_co:
        l.append(_chk(0, 3, "재무: 금융업 — 제외", na=True))
    elif debt:
        dv = debt[-1]
        l.append(_chk(3 if dv <= 50 else 2 if dv <= 100 else 0, 3, f"재무: 부채비율 {dv:.0f}% (린치: 빚이 적어야 불황을 견딤)", ok=dv <= 100))
    else:
        l.append(_chk(0, 3, "재무 데이터 없음"))
    nc = _lastv(F["netcash"])
    if nc is not None and mcap_eok:
        ncx = nc if not F["us"] else None
        if ncx is not None:
            r_ = ncx / mcap_eok
            l.append(_chk(2 if r_ >= 0.3 else 1 if r_ >= 0.1 else 0, 2, f"순현금 = 시총의 {r_ * 100:.0f}% (많을수록 주가 바닥이 단단)", ok=r_ >= 0.1))
        else:
            l.append(_chk(0, 2, "순현금 비교: 해외 종목 단위 달라 제외", na=True))
    else:
        l.append(_chk(0, 2, "순현금 데이터 없음"))
    iv, sv2 = _last(F["inv"], 2), _last(sales, 2)
    if len(iv) == 2 and len(sv2) == 2 and iv[0] and sv2[0]:
        ig, sg2 = iv[1] / iv[0] - 1, sv2[1] / sv2[0] - 1
        ok = ig <= sg2 + 0.05
        l.append(_chk(2 if ok else 0, 2, f"재고: 재고 {ig * 100:+.0f}% vs 매출 {sg2 * 100:+.0f}% (재고가 매출보다 빨리 쌓이면 경고)", ok=ok))
    elif F["inv"] and not any(F["inv"]):
        l.append(_chk(0, 2, "재고: 재고 없는 사업", na=True))
    else:
        l.append(_chk(0, 2, "재고 데이터 없음"))
    if mcap_eok:
        small = mcap_eok < 100000
        l.append(_chk(3 if mcap_eok < 30000 else 2 if small else 0.5, 3, f"크기: 시총 {mcap_eok / 10000:.1f}조 " + ("(중소형 — 10루타 여지)" if small else "(대형 — 큰 폭 상승은 어려움)"), ok=small))
    else:
        l.append(_chk(0, 3, "크기: 시총 데이터 없음"))
    H["lynch"] = l
    T["lynch"] = ["이 회사가 왜 오를지 두 문장으로 말할 수 있는가(2분 연설)", "내가 일상·업무에서 직접 써 보고 아는 회사인가",
                  "지루하거나 사람들이 꺼리는 업종이라 아직 덜 알려졌는가", "'다각화'라는 이름으로 엉뚱한 사업을 사들이고 있지 않은가", "내부자(임원)가 사고 있는가"]

    # 🎯 애크먼 — 퍼싱스퀘어 투자 원칙: 단순·예측 가능·FCF 창출 · 진입장벽 · 높은 자본수익 · 튼튼한 재무 · 매력적 가격 · 촉매
    a = []
    fc5 = _last(F["fcf"], 5)
    if len(fc5) >= 3:
        npos = sum(1 for v in fc5 if v > 0)
        a.append(_chk(4 if npos == len(fc5) else 2 if npos >= len(fc5) - 1 else 0, 4, f"FCF 창출: 최근 {len(fc5)}년 중 {npos}년 플러스", ok=npos == len(fc5)))
    else:
        a.append(_chk(0, 4, "FCF: 데이터 없음"))
    rv = _last(sales, 6)
    if len(rv) >= 4:
        falls = sum(1 for a_, b_ in zip(rv, rv[1:]) if a_ and b_ < a_ * 0.9)
        a.append(_chk(3 if not falls else 1.5 if falls == 1 else 0, 3, f"예측 가능성: {len(rv)}년간 매출 10%↑ 감소 {falls}번 (경기 영향 적을수록)", ok=not falls))
    else:
        a.append(_chk(0, 3, "예측 가능성: 매출 4년치 미만"))
    if fin_co:
        a.append(_chk(0, 3, "진입장벽(이익률): 금융업 — 제외", na=True))
    elif len(om) >= 3:
        oa, rg = sum(om) / len(om), max(om) - min(om)
        pts = 3 if oa >= 15 and rg <= 7 else 1.5 if oa >= 10 else 0
        a.append(_chk(pts, 3, f"진입장벽·자본수익: 영업이익률 평균 {oa:.1f}%·변동 {rg:.1f}%p" + (f" · ROE {roe_avg:.0f}%" if roe_avg is not None else ""), ok=pts >= 3))
    else:
        a.append(_chk(0, 3, "진입장벽: 이익률 3년치 미만"))
    nc, opl = _lastv(F["netcash"]), _lastv(op)
    if fin_co:
        a.append(_chk(0, 3, "재무(레버리지): 금융업 — 제외", na=True))
    elif nc is not None and opl:
        lev = -nc / opl if nc < 0 else 0
        a.append(_chk(3 if nc >= 0 else 1.5 if lev <= 3 else 0, 3, "튼튼한 재무: " + ("순현금" if nc >= 0 else f"순차입 = 영업이익의 {lev:.1f}배") + " (빚 적게)", ok=nc >= 0 or lev <= 3))
    elif debt:
        a.append(_chk(3 if debt[-1] <= 80 else 1.5 if debt[-1] <= 150 else 0, 3, f"튼튼한 재무: 부채비율 {debt[-1]:.0f}%", ok=debt[-1] <= 150))
    else:
        a.append(_chk(0, 3, "재무 데이터 없음"))
    fl = _lastv(F["fcf"])
    if fl is not None and mcap_eok and not F["us"]:
        fy = fl / mcap_eok * 100
        a.append(_chk(4 if fy >= 6 else 2.5 if fy >= 4 else 1 if fy >= 2 else 0, 4, f"매력적 가격: FCF 수익률 {fy:.1f}% (6%↑)", ok=fy >= 4))
    elif per and per > 0:
        a.append(_chk(4 if per <= 15 else 2 if per <= 22 else 0, 4, f"매력적 가격: PER {per:.1f}배 (FCF 수익률 대신)", ok=per <= 22))
    else:
        a.append(_chk(0, 4, "가격: 데이터 없음"))
    filings = d.get("filings")
    has_f = (not F["us"]) and filings is not None and d.get("filings_ok", True)
    if has_f:
        ret = [x for x in filings if x.get("tag") in ("자사주", "배당")]
        dil = sum(1 for x in filings if x.get("tag") == "증자·CB")
        gap = bool(pbr and pbr < 1 and (roe_avg or 0) >= 8)
        pts = (2 if ret else 0) + (1 if gap else 0) - (2 if dil else 0)
        a.append(_chk(max(0, pts), 3, "촉매: " + (f"주주환원 공시 {len(ret)}건" if ret else "주주환원 공시 없음") + (" · PBR<1인데 ROE 8%↑(재평가 여지)" if gap else "") + (f" · 희석 공시 {dil}건" if dil else ""), ok=pts >= 2))
    else:
        tgt = F["target"]
        if tgt and close:
            upx = tgt / close - 1
            a.append(_chk(3 if upx >= 0.2 else 1 if upx >= 0.05 else 0, 3, f"촉매(대신 목표가 여력): {upx * 100:+.0f}% — 해외는 공시 없음", ok=upx >= 0.2))
        else:
            a.append(_chk(0, 3, "촉매: 공시·목표가 없음", na=F["us"]))
    H["ackman"] = a
    T["ackman"] = ["시장 1등이라 가격을 정할 수 있는가(지배적 위치)", "금리·원자재·규제처럼 통제 못 하는 위험에 덜 노출됐는가",
                   "가치가 드러날 계기(구조조정·분할·경영진 교체·자사주)가 보이는가", "경영진과 지배구조가 주주 편인가"]

    # 합계
    heroes, got, mx_all, av_all = [], 0, 0, 0
    for key, name, icon, theme, motto in HEROES:
        cs = H[key]
        ev = [c for c in cs if c["ok"] is not None]
        miss = [c for c in cs if c["ok"] is None and not c.get("na")]
        p, m = sum(c["pts"] for c in ev), sum(c["max"] for c in ev)
        mm = sum(c["max"] for c in miss)
        if m == 0:                                    # 판단할 데이터가 하나도 없으면 점수 없음
            heroes.append({"key": key, "name": name, "icon": icon, "theme": theme, "motto": motto, "score": None, "coverage": 0, "checks": cs, "todo": T.get(key, [])})
            continue
        p2, m2 = p + 0.5 * mm, m + mm                 # 데이터 없는 항목은 반만 인정
        got, mx_all, av_all = got + p2, mx_all + m2, av_all + m
        heroes.append({"key": key, "name": name, "icon": icon, "theme": theme, "motto": motto,
                       "score": round(p2 / m2 * 20, 1), "coverage": round(m / m2, 2), "checks": cs, "todo": T.get(key, [])})
    total = round(got / mx_all * 100, 1) if mx_all else None
    coverage = av_all / mx_all if mx_all else 0        # 해당 기준 중 실제 데이터가 있는 비율
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
    return {"total": total, "coverage": round(coverage, 2), "grade": grade, "note": note, "heroes": heroes, "src": F["src"],
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
