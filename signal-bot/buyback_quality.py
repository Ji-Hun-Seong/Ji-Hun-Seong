"""buyback_quality.py — '좋은 자사주 공시' 판별 (토스봇 실매매 + 장중 공시 알림 공용, requests만 사용)

매수 = [① 52주 고점 대비 -30% 이하  또는  ② 1년 안 재매입]  그리고  [③ 매입 규모가 시총의 1% 이상 (금액 모르면 통과)]
  백테스트(README 8차, 2014~2026 자사주 원공시 1,315건, 다음 날 시가 → 10일 초과수익):
  ①② 둘 다 아님: IS -0.6%·OOS 0.0% → 제외 / 규모 1% 미만: IS +0.1%·OOS +0.5% → 제외
  최종: 거래당 IS +1.7%·OOS +2.6%, 7종목 포트폴리오 연 20.4%·MDD -27%·Sharpe 1.64, 손실 연도 없음
검증해 보니 효과 없어서 매수 이유에서 뺀 것(표시만 함): 시총 3% 이상(1~3%와 차이 없음), 소각 목적,
  밸류업 약속 이행(17건 +0.3%), 저PBR(거래당은 조금 낫지만 기회가 줄어 연수익 하락).
밸류업 계획 공시 자체도 매수하지 않음: 공시 후 60일 -4.4%(t -3.3, 2024~).
"""
from __future__ import annotations

import io
import re
import time
import zipfile
from datetime import datetime, timedelta

import requests

DART = "https://opendart.fss.or.kr/api"
UA = {"User-Agent": "Mozilla/5.0"}
BB_PAT = r"자기주식취득신탁계약체결결정|^(?:주요사항보고서\()?자기주식취득결정"
VU_PAT = r"기업가치제고계획"
SIZE_MIN = 0.01        # 시총 대비 1% 미만이면 제외
BIG = 0.03             # 아빠 기준(연 3%) — 알림 표시용
DD_MAX = -0.30         # 52주 고점 대비 -30%
NUM = r"(-?[\d,]+(?:\.\d+)?)"


def _n(x):
    return float(str(x).replace(",", ""))


def doc_text(rcept_no: str, key: str) -> str:
    """DART 원문(zip 안 XML)을 태그 없는 텍스트로. 실패하면 ''."""
    try:
        r = requests.get(f"{DART}/document.xml", params={"crtfc_key": key, "rcept_no": rcept_no}, timeout=30)
        z = zipfile.ZipFile(io.BytesIO(r.content))
        raw = " ".join(z.read(n).decode("utf-8", "ignore") for n in z.namelist())
    except Exception:
        return ""
    t = re.sub(r"<[^>]+>", " ", raw)
    t = re.sub(r"&nbsp;|&#160;", " ", t)
    return re.sub(r"\s+", " ", t)


def bb_amount(text: str, trust: bool, price: float | None = None) -> float | None:
    """자사주 취득결정·신탁계약 원문의 금액(원). 금액이 없으면 예정 주식수 × 가격."""
    if not text:
        return None
    m = (re.search(r"계약금액\s*\(원\)\s*" + NUM, text) if trust else
         re.search(r"취득예(?:상|정)금액\s*\(원\)\s*보통주식\s*" + NUM, text))
    if m and _n(m.group(1)) > 0:
        return _n(m.group(1))
    m = re.search(r"취득예정주식\s*(?:수)?\s*\(주\)\s*보통주식\s*" + NUM, text)
    if m and price and _n(m.group(1)) > 0:
        return _n(m.group(1)) * price
    return None


def _won(num: str, unit: str) -> float:
    v = _n(num)
    return v * (1e12 if unit == "조" else 1e8 if unit == "억" else 1e6 if unit == "백만" else 1)


def pledge_per_year(text: str) -> float | None:
    """밸류업 계획 원문에서 '연간' 자사주 매입 약속 금액(원). 예: '2027~2029년 자사주 매입·소각 500억원' → 166.7억.
    연도 범위가 없으면 1년으로 본다. 여러 개면 가장 큰 값."""
    best = None
    for m in re.finditer(r"자사주|자기주식", text or ""):
        win = text[max(0, m.start() - 80): m.end() + 120]
        am = re.search(r"([\d,]+(?:\.\d+)?)\s*(조|억|백만)\s*원", win)
        if not am:
            continue
        if not re.search(r"매입|취득|소각", win):
            continue
        years = 1
        yr = re.search(r"(20\d\d)\s*년?\s*[~\-–∼]\s*(?:20)?(\d\d)\s*년?", win)
        if yr:
            y1, y2 = int(yr.group(1)), int(yr.group(2)) % 100 + 2000
            if 0 <= y2 - y1 <= 9:
                years = y2 - y1 + 1
        v = _won(am.group(1), am.group(2)) / years
        best = v if best is None or v > best else best
    return best


def mcap(code: str) -> float | None:
    """네이버 시가총액(원)."""
    try:
        j = requests.get(f"https://m.stock.naver.com/api/stock/{code}/integration", headers=UA, timeout=15).json()
    except Exception:
        return None
    for it in j.get("totalInfos", []):
        if it.get("code") == "marketValue":
            s = (it.get("value") or "").replace(",", "")
            jo, eok = re.search(r"([\d.]+)조", s), re.search(r"([\d.]+)억", s)
            v = (float(jo.group(1)) * 1e12 if jo else 0) + (float(eok.group(1)) * 1e8 if eok else 0)
            return v or None
    return None


def corp_filings(corp_code: str, key: str, bgn: str, end: str) -> list:
    """한 회사의 주요사항(B)·거래소(I) 원공시 목록(정정 제외)."""
    out = []
    for ty in ("B", "I"):
        try:
            j = requests.get(f"{DART}/list.json", params={"crtfc_key": key, "corp_code": corp_code, "pblntf_ty": ty,
                             "bgn_de": bgn, "end_de": end, "page_count": 100}, timeout=20).json()
        except Exception:
            continue
        out += [x for x in j.get("list", []) if not re.sub(r"\s+", "", x.get("report_nm", "")).startswith("[")]
        time.sleep(0.2)
    return out


def assess(*, code: str, corp_code: str | None, rcept_no: str, trust: bool, key: str, day: str,
           closes: list | None = None, price: float | None = None, text: str | None = None) -> dict:
    """closes: 공시 전날까지 일봉 종가(최근 250개 이상이면 52주 고점 계산). day: YYYYMMDD.
    반환: good, reasons(통과 이유), notes(참고), pct, dd, repeat, pledge_pct"""
    r = {"good": False, "reasons": [], "notes": []}
    if closes and len(closes) >= 60:
        hi = max(closes[-250:])
        r["dd"] = closes[-1] / hi - 1
        if r["dd"] <= DD_MAX:
            r["reasons"].append(f"52주 고점 대비 {r['dd']:.0%} (많이 빠진 뒤 매입)")
        else:
            r["notes"].append(f"52주 고점 대비 {r['dd']:.0%}")
    price = price or (closes[-1] if closes else None)
    text = text if text is not None else doc_text(rcept_no, key)
    amt = bb_amount(text, trust, price)
    cap = mcap(code)
    if amt and cap:
        r["pct"] = amt / cap
        r["notes"].append(f"매입 규모 {amt / 1e8:,.0f}억 = 시총 {cap / 1e8:,.0f}억의 {r['pct']:.1%}"
                          + (" (시총 3%↑ 큰 매입)" if r["pct"] >= BIG else " (1% 미만 → 제외)" if r["pct"] < SIZE_MIN else ""))
    if corp_code:
        d = datetime.strptime(day, "%Y%m%d")
        hist = corp_filings(corp_code, key, (d - timedelta(days=730)).strftime("%Y%m%d"), (d - timedelta(days=1)).strftime("%Y%m%d"))
        one_y = (d - timedelta(days=365)).strftime("%Y%m%d")
        prev = [x for x in hist if x.get("rcept_dt", "") >= one_y and re.search(BB_PAT, re.sub(r"\s+", "", x.get("report_nm", "")))]
        r["repeat"] = bool(prev)
        if prev:
            r["reasons"].append(f"1년 안 재매입(이전 {len(prev)}건)")
        vu = [x for x in hist if re.search(VU_PAT, re.sub(r"\s+", "", x.get("report_nm", "")))]
        if vu:
            vu.sort(key=lambda x: x["rcept_no"])
            yearly = pledge_per_year(doc_text(vu[-1]["rcept_no"], key))
            if yearly and cap:
                r["pledge_pct"] = yearly / cap
                msg = f"밸류업 약속 연 {yearly / 1e8:,.0f}억(시총의 {r['pledge_pct']:.1%}) 이행"
                r["notes"].append(msg)
    r["small"] = r.get("pct") is not None and r["pct"] < SIZE_MIN
    r["good"] = bool(r["reasons"]) and not r["small"]
    return r


def valueup_alert(text: str, code: str) -> dict | None:
    """밸류업 계획 공시에서 연 시총 3% 이상 자사주 매입 약속이 있으면 요약 dict (알림용, 매수 안 함)."""
    y = pledge_per_year(text)
    cap = mcap(code)
    if not y or not cap:
        return None
    return {"yearly": y, "cap": cap, "pct": y / cap, "big": y / cap >= BIG}
