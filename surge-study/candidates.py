"""candidates.py — '내일 급등할 수 있는 후보' 10선 (collect.py가 장 마감 후 호출)

아직 학습 데이터가 1~2주뿐이라 v0는 **규칙 점수**입니다. 급등 전에 자주 보이는 신호(PATTERNS.md 체크리스트)를
점수로 합산하고, 다음 날 실제로 얼마나 올랐는지 매일 채점해 `candidates/날짜.json`에 같이 남깁니다.
한 달치가 쌓이면 universe/ 데이터로 학습한 모형 점수로 바꿉니다 (README '한 달 뒤 계획').

점수(100점) = 재료 35 + 거래량 선행 20 + 차트 에너지 25 + 종가 강도 10 + 유동성 10 − 감점 − 추격
  v1(2026-11-03): '이미 한참 오른 종목'이 위로 올라오던 문제 수정 — 오늘 많이 오른 공시는 이미 반영된 것으로 보고 재료 할인,
                  최근 5일·20일 상승폭·연속 상승·밴드 상단 돌파는 '추격' 감점, 20일 횡보(아직 덜 오름)는 가산
  재료        : 오늘 DART 공시 — 공급계약·무상증자·공개매수 > 임상·허가·특허 > 자사주 > 실적(방향 모름)
  거래량 선행  : 오늘 거래량이 20일 평균의 2·3·5배↑인데 주가는 아직 덜 오름(−2% ~ +9%) = '매집'
  차트 에너지  : 볼린저 스퀴즈(밴드폭 6개월 하위 15%), 상단 밴드 근처, 52주 고점 근처, 정배열
  종가 강도    : 종가가 하루 고저 범위 위쪽(고가 마감)
  유동성       : 거래대금 (너무 작으면 신호가 아니라 잡음)
  추격 감점    : 오늘 +4%↑, 5일 +8%↑, 20일 +15%↑, 4일 연속 상승, 볼린저 상단 돌파
  감점·제외    : 오늘 이미 +10%↑ 또는 5일 +30%↑(제외), RSI 80↑, 긴 윗꼬리, 유상증자·CB, 거래소 경고·과열, 1,000원 미만, 우선주

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
METHOD = "v2-rules-news-2026-11-04"
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
    # 같은 공시라도 덩치 큰 종목은 덜 움직임 (조선·건설 대형주는 공급계약을 거의 매주 냄)
    tv20 = f.get("tv20_avg") or 0
    if cat and tv20 >= 300e8:
        cat *= 0.4
    elif cat and tv20 >= 100e8:
        cat *= 0.7
    vr, chg = tb.get("vol_ratio") or 0, tb.get("chg") or 0
    priced = ""
    if cat and chg >= 8:                      # 공시가 장중에 나와 오늘 이미 크게 올랐으면 재료는 상당 부분 반영
        cat *= 0.3; priced = f" (오늘 {chg:+.1f}% — 이미 반영)"
    elif cat and chg >= 5:
        cat *= 0.6; priced = f" (오늘 {chg:+.1f}% — 일부 반영)"
    parts["재료"] = round(cat)
    if tags:
        why.append("오늘 공시: " + "·".join(tags) + (" (대형주라 반영 축소)" if tv20 >= 100e8 else "") + priced)
    # 거래량 선행
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
    r5, r20, up = f.get("ret5"), f.get("ret20"), f.get("up_days") or 0
    if pb is not None and 0.8 <= pb <= 1.0:                # 상단에 '붙은' 것만 (돌파해 버린 건 추격 쪽)
        e += 8; why.append(f"상단 밴드 근처(%b {pb:.2f})")
    if fh is not None and fh >= -0.05 and (r20 is None or r20 < 0.15):   # 횡보 끝 고점 근처만 (급등 후 고점은 제외)
        e += 7; why.append("52주 고점 근처" if fh < 0 else "52주 신고가")
    if r20 is not None and -0.10 <= r20 <= 0.10 and chg < 4:
        e += 5; why.append(f"20일간 {r20 * 100:+.0f}% 횡보(아직 덜 오름)")
    if f.get("ma_aligned"):
        e += 5; why.append("정배열")
    if e and chg <= -3:                       # 오늘 크게 빠졌으면 차트 신호는 반만 (떨어지는 칼날)
        e *= 0.5; warn.append(f"오늘 {chg:+.1f}% 하락")
    parts["차트"] = round(min(25, e))
    # 종가 강도
    cp = tb.get("close_pos")
    parts["종가"] = 10 if cp is not None and cp >= 0.8 and 0 < chg < 5 else 5 if cp is not None and cp >= 0.6 and chg > 0 else 0
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
    # 추격 — 이미 오른 만큼 깎음
    run = 0
    if chg >= 7:
        run -= 10
    elif chg >= 4:
        run -= 5
    if r5 is not None and r5 >= 0.08:
        run -= 20 if r5 >= 0.25 else 12 if r5 >= 0.15 else 5
        warn.append(f"5일 {r5 * 100:+.0f}%")
    if r20 is not None and r20 >= 0.15:
        run -= 20 if r20 >= 0.5 else 12 if r20 >= 0.3 else 5
        warn.append(f"20일 {r20 * 100:+.0f}%")
    if up >= 4:
        run -= 5; warn.append(f"{up}일 연속 상승")
    if pb is not None and pb > 1.0:
        run -= 5; warn.append(f"볼린저 상단 돌파(%b {pb:.2f})")
    parts["추격"] = run
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
        if tb["close"] < 1000 or tb["tv"] < 5e8 or tb["chg"] >= 10:
            continue
        f = features(df)                      # 오늘 종가까지 (내일 기준으로는 '전날까지' 정보)
        if (f.get("ret5") or 0) >= 0.30:      # 5일 새 +30%↑ = 이미 급등한 종목 → 후보 아님
            continue
        fl = [x for x in filings.get(c, []) if x.get("date") == f"{today:%Y%m%d}"]
        total, parts, why, warn = score_row(f, tb, fl)
        if total <= -50:                      # 거래소 경고 등 → 제외
            continue
        rows.append({"code": c, "name": nm["name"], "market": nm["market"], "score": round(total, 1), "parts": parts,
                     "why": why, "warn": warn, "close": tb["close"], "chg": round(tb["chg"], 2), "tv": tb["tv"],
                     "vol_ratio": round(tb["vol_ratio"] or 0, 2), "close_pos": round(tb["close_pos"], 2),
                     "pctb": f.get("pctb"), "bw_pctile": f.get("bw_pctile"), "rsi14": f.get("rsi14"),
                     "from_high": f.get("from_high"), "ma_aligned": f.get("ma_aligned"),
                     "ret5": f.get("ret5"), "ret20": f.get("ret20"),
                     "filings": [{"title": x["title"], "rcept_no": x["rcept_no"]} for x in fl[:5]]})
    rows.sort(key=lambda r: (-r["score"], -r["tv"]))
    return {"date": tstr, "for": "다음 거래일", "method": METHOD, "n_scored": len(rows), "candidates_all": rows}


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


def build_index():
    """candidates/index.json — 날짜별 요약(대시보드 '지난 날짜 보기'용). 저장할 때마다 전체를 다시 만든다"""
    daily = os.path.join(HERE, "data", "daily")
    rows = []
    for f in sorted(os.listdir(OUT), reverse=True):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}\.json", f):
            continue
        try:
            c = json.load(open(os.path.join(OUT, f), encoding="utf-8"))
        except Exception:
            continue
        g = c.get("graded") or {}
        n_surge = None
        df = os.path.join(daily, f)
        if os.path.exists(df):
            try:
                n_surge = (json.load(open(df, encoding="utf-8")).get("context") or {}).get("n_surge")
            except Exception:
                pass
        rows.append({"date": c["date"], "method": c.get("method"), "n_scored": c.get("n_scored"),
                     "top": [x["name"] for x in c.get("candidates", [])[:3]], "n_surge": n_surge,
                     "graded": {k: g.get(k) for k in ("avg", "up", "n", "hit10", "market_avg")} if g else None})
    json.dump({"dates": rows}, open(os.path.join(OUT, "index.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return rows


def save(out: dict, prev: dict | None):
    os.makedirs(OUT, exist_ok=True)
    out["prev"] = prev
    path = os.path.join(OUT, f"{out['date']}.json")
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)
    json.dump(out, open(os.path.join(OUT, "latest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)
    try:
        build_index()
    except Exception as e:
        print("index.json 실패:", e)
    return path


# ── 뉴스 재료 (v2) — 구글 뉴스 최근 2일 제목 ─────────────────────
NEWS_POS = [   # (태그, 정규식, 점수) — 한 종목은 가장 큰 재료 점수 + 재료 종류가 2개 이상이면 +5
    ("임상·허가", r"FDA|품목 ?허가|허가 ?획득|임상 ?(성공|3상|결과|승인)|기술 ?이전|라이선스 ?아웃", 18),
    ("수주·계약", r"수주|공급 ?계약|계약 ?체결|납품 ?계약|단일판매", 15),
    ("실적", r"흑자 ?전환|사상 ?최대|역대 ?최대|어닝 ?서프라이즈|최대 ?실적|영업이익.{0,8}(급증|증가|껑충)", 15),
    ("M&A·지배구조", r"인수|합병|M&A|경영권|공개매수|지분 ?인수", 15),
    ("신기술·신제품", r"세계 ?최초|국내 ?최초|국산화|개발 ?성공|신제품|출시|특허", 8),
    ("정책·수혜", r"정부|정책|국책|지원책|수혜|규제 ?완화|법안 ?통과", 8),
]
NEWS_NEG = [
    ("악재 뉴스", r"유상증자|전환사채|횡령|배임|소송|하한가|급락|적자 ?(전환|확대)|감사의견|상장폐지|불성실|압수수색|리콜", -15),
]
NEWS_PRICED = r"상한가|급등|신고가|불기둥|폭등"
THEMES = ["AI", "반도체", "HBM", "2차전지", "배터리", "로봇", "원전", "방산", "조선", "바이오", "제약", "우주", "항공",
          "자율주행", "전기차", "수소", "태양광", "풍력", "게임", "엔터", "화장품", "식품", "건설", "철강", "금융", "보안",
          "양자", "초전도", "스테이블코인", "가상자산", "비트코인", "남북", "광통신", "데이터센터", "전력", "변압기", "의료기기"]
NEWS_TOP = 120          # 공시·거래량·차트 점수 상위 몇 종목만 뉴스를 받아 다시 채점 (요청 수 제한)


def news_score(titles: list[str], filing_tags: list[str], chg: float, hot: list[str]) -> tuple[float, list[str], list[str], list[str]]:
    """→ (뉴스 점수, 이유, 경고, 테마)"""
    why, warn = [], []
    hit = [(tag, pts) for tag, pat, pts in NEWS_POS if any(re.search(pat, t) for t in titles)]
    pts = 0
    if hit:
        tags = [t for t, _ in hit]
        pts = max(p for _, p in hit) + (5 if len(hit) >= 2 else 0)
        same = {"수주·계약": "공급계약", "실적": "실적", "M&A·지배구조": "공개매수·합병", "임상·허가": "임상·허가", "신기술·신제품": "특허"}
        ft = " ".join(filing_tags)
        dup = any(same.get(t) and same[t] in ft for t in tags)            # 같은 재료를 공시로 이미 셌으면 뉴스는 덜 줌
        tags_new = [t for t in tags if not (same.get(t) and same[t] in ft)]
        if dup and tags_new:                                               # 공시에 없던 새 재료가 뉴스에 있으면 그건 인정
            pts = max(p for t, p in hit if t in tags_new)
            dup = False
        if dup:
            pts = min(pts, 6)
        why.append("뉴스: " + "·".join(tags) + (" (공시와 같은 재료)" if dup else ""))
    for tag, pat, p in NEWS_NEG:
        if any(re.search(pat, t) for t in titles):
            pts += p; warn.append(tag)
    if len(titles) >= 8:
        pts += 5; why.append(f"이틀 새 기사 {len(titles)}건(관심 급증)")
    if any(re.search(NEWS_PRICED, t) for t in titles):
        pts *= 0.5; warn.append("뉴스에 이미 '급등·상한가' 기사")
    if chg >= 8:
        pts *= 0.3
    elif chg >= 5:
        pts *= 0.6
    th = [t for t in THEMES if any(t in x for x in titles)]
    hot_hit = [t for t in th if t in hot]
    if hot_hit:
        pts += 8; why.append("오늘 급등 테마 동반: " + "·".join(hot_hit[:2]))
    return round(min(25, pts), 1), why, warn, th


def add_news(out: dict, news_fn, hot: list[str]):
    """상위 NEWS_TOP 종목만 뉴스 제목을 받아 '뉴스' 점수를 더하고 다시 정렬"""
    from concurrent.futures import ThreadPoolExecutor
    rows = out["candidates_all"]
    top = rows[:NEWS_TOP]
    def one(r):
        try:
            return r, news_fn(r["name"], 15)
        except Exception:
            return r, []
    with ThreadPoolExecutor(6) as ex:
        got = list(ex.map(one, top))
    for r, nw in got:
        titles = [x["title"] for x in nw]
        pts, why, warn, th = news_score(titles, [w for w in r["why"] if w.startswith("오늘 공시")], r["chg"], hot)
        r["parts"]["뉴스"] = pts
        r["score"] = round(r["score"] + pts, 1)
        r["why"] = why + r["why"] if pts > 0 else r["why"] + why
        r["warn"] += warn
        r["themes"] = th
        r["news"] = [{"title": x["title"], "source": x.get("source"), "link": x.get("link"), "date": x.get("date")} for x in nw[:3]]
        r["n_news"] = len(nw)
    rows.sort(key=lambda r: (-r["score"], -r["tv"]))
    out["hot_themes"] = hot


def run(frames, names, filings, today, features, today_bar, news_fn=None, hot_themes=None):
    chg = {}
    for c, df in frames.items():
        if df.index[-1] == today and len(df) > 1:
            chg[c] = float(df["close"].iloc[-1] / df["close"].iloc[-2] - 1) * 100
    prev = grade_prev(today, chg)
    out = build(frames, names, filings, today, features, today_bar)
    if news_fn:
        add_news(out, news_fn, hot_themes or [])
    out["candidates"] = out.pop("candidates_all")[:N_KEEP]
    return save(out, prev), out


if __name__ == "__main__":
    if "--show" in sys.argv:
        d = sys.argv[sys.argv.index("--show") + 1] if len(sys.argv) > sys.argv.index("--show") + 1 else "latest"
        p = json.load(open(os.path.join(OUT, f"{d}.json"), encoding="utf-8"))
        print(p["date"], p["method"], "채점 대상", p["n_scored"])
        for i, r in enumerate(p["candidates"][:N_SHOW], 1):
            print(f"{i:2}. {r['name']:<12} {r['score']:5.1f}  {r['chg']:+.1f}%  {' / '.join(r['why'])}  {' '.join(r['warn'])}")
