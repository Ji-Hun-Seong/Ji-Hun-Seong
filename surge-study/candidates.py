"""candidates.py — '내일 급등할 수 있는 후보' 10선 (collect.py가 장 마감 후 호출)

아직 학습 데이터가 1~2주뿐이라 v0는 **규칙 점수**입니다. 급등 전에 자주 보이는 신호(PATTERNS.md 체크리스트)를
점수로 합산하고, 다음 날 실제로 얼마나 올랐는지 매일 채점해 `candidates/날짜.json`에 같이 남깁니다.
한 달치가 쌓이면 universe/ 데이터로 학습한 모형 점수로 바꿉니다 (README '한 달 뒤 계획').

점수(100점) = 재료 35 + 거래량 선행 20 + 차트 에너지 25 + 종가 강도 10 + 유동성 10 − 감점
  재료        : 오늘 DART 공시 — 공급계약·무상증자·공개매수 > 임상·허가·특허 > 자사주 > 실적(방향 모름)
  거래량 선행  : 오늘 거래량이 20일 평균의 2·3·5배↑인데 주가는 아직 덜 오름(−2% ~ +9%) = '매집'
  차트 에너지  : 볼린저 스퀴즈(밴드폭 6개월 하위 15%), 상단 밴드 근처, 52주 고점 근처, 정배열
  종가 강도    : 종가가 하루 고저 범위 위쪽(고가 마감)
  유동성       : 거래대금 (너무 작으면 신호가 아니라 잡음)
  감점·제외    : 오늘 이미 +15%↑(추격), RSI 80↑, 긴 윗꼬리, 유상증자·CB, 거래소 경고·과열, 1,000원 미만, 우선주

  python surge-study/candidates.py --show 2026-11-03     # 저장된 후보 보기
"""
from __future__ import annotations

import json
import os
import re
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "candidates")
METHOD = "v0-rules-2026-11"
N_SHOW, N_KEEP = 10, 30

CAT_RULES = [   # (태그, 정규식, 점수)
    ("공급계약", r"단일판매|공급계약", 35),
    ("무상증자", r"무상증자", 32),
    ("공개매수·합병", r"공개매수|합병결정|최대주주변경", 28),
    ("임상·허가", r"임상|품목허가|기술이전|라이선스", 28),
    ("특허", r"특허", 15),
    ("자사주", r"자기주식취득|주식소각|신탁계약체결", 20),
    ("실적", r"영업\(잠정\)실적|잠정실적|매출액또는손익구조", 18),
    ("시설투자", r"신규시설투자|유형자산양수", 12),
]
NEG_RULES = [
    ("유상증자·CB", r"유상증자|전환사채|신주인수권부사채|교환사채", -20),
    ("거래소 경고", r"투자경고|투자위험|단기과열|매매거래정지|불성실공시|관리종목", -100),
]


def _clip(x, lo, hi):
    return max(lo, min(hi, x))


def score_row(f: dict, tb: dict, filings: list[dict]) -> tuple[float, dict, list[str], list[str]]:
    """f = 오늘 종가까지의 특징, tb = 오늘 봉, filings = 오늘 공시. → (점수, 항목별 점수, 이유, 경고)"""
    parts, why, warn = {}, [], []
    titles = [re.sub(r"\s", "", x["title"]) for x in filings]
    # 재료
    cat, tags = 0, []
    for tag, pat, pts in CAT_RULES:
        if any(re.search(pat, t) for t in titles):
            tags.append(tag)
            cat = max(cat, pts)
    neg = 0
    for tag, pat, pts in NEG_RULES:
        if any(re.search(pat, t) for t in titles):
            warn.append(tag)
            neg += pts
    parts["재료"] = cat
    if tags:
        why.append("오늘 공시: " + "·".join(tags))
    # 거래량 선행
    vr, chg = tb.get("vol_ratio") or 0, tb.get("chg") or 0
    v = 0
    if -2 <= chg <= 9:
        v = 20 if vr >= 5 else 15 if vr >= 3 else 10 if vr >= 2 else 4 if vr >= 1.5 else 0
    elif 9 < chg < 15 and vr >= 3:
        v = 8
    parts["거래량"] = v
    if v >= 10:
        why.append(f"거래량 {vr:.1f}배인데 주가는 {chg:+.1f}%")
    # 차트 에너지
    e = 0
    bp, pb, fh = f.get("bw_pctile"), f.get("pctb"), f.get("from_high")
    if bp is not None and bp <= 0.15:
        e += 10; why.append(f"볼린저 스퀴즈(밴드폭 6개월 하위 {bp * 100:.0f}%)")
    if pb is not None and 0.8 <= pb <= 1.15:
        e += 8; why.append(f"상단 밴드 근처(%b {pb:.2f})")
    if fh is not None and fh >= -0.05:
        e += 7; why.append("52주 고점 근처" if fh < 0 else "52주 신고가")
    if f.get("ma_aligned"):
        e += 5; why.append("정배열")
    parts["차트"] = min(25, e)
    # 종가 강도
    cp = tb.get("close_pos")
    parts["종가"] = 10 if cp is not None and cp >= 0.8 and chg > 0 else 5 if cp is not None and cp >= 0.6 and chg > 0 else 0
    if parts["종가"] == 10:
        why.append("고가 근처 마감")
    # 유동성
    tv = tb.get("tv") or 0
    parts["유동성"] = 10 if tv >= 50e8 else 6 if tv >= 20e8 else 3 if tv >= 10e8 else 0
    # 감점
    pen = neg
    rsi = f.get("rsi14")
    if rsi is not None and rsi >= 80:
        pen -= 10; warn.append(f"RSI {rsi:.0f} 과열")
    if (tb.get("upper_wick") or 0) >= 5:
        pen -= 5; warn.append(f"윗꼬리 {tb['upper_wick']:.1f}%")
    parts["감점"] = pen
    total = sum(parts.values())
    return total, parts, why, warn


def build(frames: dict, names: pd.DataFrame, filings: dict, today: pd.Timestamp, features, today_bar) -> dict:
    """collect.py에서 호출. frames = {코드: 일봉(오늘 포함)}"""
    rows = []
    tstr = f"{today:%Y-%m-%d}"
    for c, df in frames.items():
        if df.index[-1] != today or len(df) < 61:
            continue
        nm = names.loc[c]
        if bool(nm["pref"]):
            continue
        tb = today_bar(df)
        if tb["close"] < 1000 or tb["tv"] < 5e8 or tb["chg"] >= 15:
            continue
        f = features(df)                      # 오늘 종가까지 (내일 기준으로는 '전날까지' 정보)
        fl = [x for x in filings.get(c, []) if x.get("date") == f"{today:%Y%m%d}"]
        total, parts, why, warn = score_row(f, tb, fl)
        if total <= -50:                      # 거래소 경고 등 → 제외
            continue
        rows.append({"code": c, "name": nm["name"], "market": nm["market"], "score": round(total, 1), "parts": parts,
                     "why": why, "warn": warn, "close": tb["close"], "chg": round(tb["chg"], 2), "tv": tb["tv"],
                     "vol_ratio": round(tb["vol_ratio"] or 0, 2), "close_pos": round(tb["close_pos"], 2),
                     "pctb": f.get("pctb"), "bw_pctile": f.get("bw_pctile"), "rsi14": f.get("rsi14"),
                     "from_high": f.get("from_high"), "ma_aligned": f.get("ma_aligned"),
                     "filings": [{"title": x["title"], "rcept_no": x["rcept_no"]} for x in fl[:5]]})
    rows.sort(key=lambda r: (-r["score"], -r["tv"]))
    return {"date": tstr, "for": "다음 거래일", "method": METHOD, "n_scored": len(rows), "candidates": rows[:N_KEEP]}


def grade_prev(today: pd.Timestamp, chg_today: dict[str, float]) -> dict | None:
    """직전 후보 파일을 오늘 등락률로 채점"""
    if not os.path.isdir(OUT):
        return None
    prev = sorted(f for f in os.listdir(OUT) if f.endswith(".json") and f[:10] < f"{today:%Y-%m-%d}")
    if not prev:
        return None
    p = json.load(open(os.path.join(OUT, prev[-1]), encoding="utf-8"))
    res = []
    for r in p["candidates"][:N_SHOW]:
        ch = chg_today.get(r["code"])
        res.append({"code": r["code"], "name": r["name"], "score": r["score"], "next_chg": None if ch is None else round(ch, 2)})
    got = [x["next_chg"] for x in res if x["next_chg"] is not None]
    allv = list(chg_today.values())
    summary = {"from": p["date"], "results": res, "n": len(got),
               "hit10": sum(1 for x in got if x >= 10), "up": sum(1 for x in got if x > 0),
               "avg": round(sum(got) / len(got), 2) if got else None,
               "market_avg": round(sum(allv) / len(allv), 2) if allv else None}
    p["graded"] = {k: v for k, v in summary.items() if k != "from"}
    json.dump(p, open(os.path.join(OUT, prev[-1]), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)
    return summary


def save(out: dict, prev: dict | None):
    os.makedirs(OUT, exist_ok=True)
    out["prev"] = prev
    path = os.path.join(OUT, f"{out['date']}.json")
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)
    json.dump(out, open(os.path.join(OUT, "latest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)
    return path


def run(frames, names, filings, today, features, today_bar):
    chg = {}
    for c, df in frames.items():
        if df.index[-1] == today and len(df) > 1:
            chg[c] = float(df["close"].iloc[-1] / df["close"].iloc[-2] - 1) * 100
    prev = grade_prev(today, chg)
    out = build(frames, names, filings, today, features, today_bar)
    return save(out, prev), out


if __name__ == "__main__":
    if "--show" in sys.argv:
        d = sys.argv[sys.argv.index("--show") + 1] if len(sys.argv) > sys.argv.index("--show") + 1 else "latest"
        p = json.load(open(os.path.join(OUT, f"{d}.json"), encoding="utf-8"))
        print(p["date"], p["method"], "채점 대상", p["n_scored"])
        for i, r in enumerate(p["candidates"][:N_SHOW], 1):
            print(f"{i:2}. {r['name']:<12} {r['score']:5.1f}  {r['chg']:+.1f}%  {' / '.join(r['why'])}  {' '.join(r['warn'])}")
