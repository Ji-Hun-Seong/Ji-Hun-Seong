"""급등주 패턴 수집기 — 평일 장 마감 후 GitHub Actions에서 실행

하는 일
  1. 코스피·코스닥 전 종목 일봉(네이버) → 오늘 급등주 선정(+10% 이상, 보통주, 거래대금 기준)
  2. 전 종목의 '어제까지' 차트 특징을 저장 → 한 달 뒤 "급등 전날 무엇이 달랐나" 학습용 (급등 안 한 종목과 비교)
  3. 급등주마다 오늘·전일 DART 공시와 최근 뉴스 제목(구글 뉴스 RSS) 수집 → 재료(촉매) 자동 분류
  4. 과거 급등주의 이후 수익률(+1·+3·+5·+10거래일) 추적 → 급등 후 이어지는지/되돌리는지
  5. 일일 리포트(마크다운 + 차트 그림) 생성, 텔레그램 개인 채팅 요약

저장 (surge-study/data/)
  universe/YYYY-MM-DD.csv.gz   전 종목: 오늘 등락·거래대금 + 어제까지의 특징 (학습용 원천)
  daily/YYYY-MM-DD.json        급등주 상세(특징·공시·뉴스·재료)
  surges.csv                   급등주 누적 표 (+ 이후 수익률)
  reports/YYYY-MM-DD.md, img/  사람이 읽는 리포트

  python surge-study/collect.py                 # 오늘
  python surge-study/collect.py --date 2026-11-03 --no-send
환경변수: DART_API_KEY, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID(개인 채팅만)
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import html
import io
import json
import os
import re
import sys
import time
import zipfile
from xml.etree import ElementTree

import numpy as np
import pandas as pd
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
KST = dt.timezone(dt.timedelta(hours=9))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36"}
REPO_URL = "https://github.com/Ji-Hun-Seong/Ji-Hun-Seong/blob/main/surge-study"

SURGE_PCT = 10.0          # 급등 기준: 전일 종가 대비 +10% 이상
BIG_TV, BIG_PCT = 300e8, 5.0   # 대형주(평소 거래대금 300억↑)는 +5%만 올라도 급등으로 기록 — 삼성SDI 같은 대형주 호재를 놓치지 않게
                               # (research/largecap_backtest.md: 대형주 '다음 날 +5%'는 전날 지표로 예측이 안 돼서, 예측 대신 '기록·공부'용)
MIN_TV = 10e8             # 리포트 상위 정렬 시 '의미 있는' 거래대금 기준 10억 (그 아래도 저장은 함)
FOLLOW = (1, 3, 5, 10)    # 이후 수익률 추적 거래일


# ── 1. 종목 목록 ─────────────────────────────────────
def listing() -> pd.DataFrame:
    rows = []
    for mkt in ("KOSPI", "KOSDAQ"):
        for page in range(1, 60):
            j = requests.get(f"https://m.stock.naver.com/api/stocks/marketValue/{mkt}",
                             params={"page": page, "pageSize": 100}, headers=UA, timeout=20).json()
            items = j.get("stocks", []) if isinstance(j, dict) else j
            if not items:
                break
            for it in items:
                name = it.get("stockName", "")
                if it.get("stockEndType") != "stock":          # ETF·ETN·리츠 등 제외
                    continue
                if "스팩" in name or re.search(r"\d+호$", name):  # 스팩 제외
                    continue
                rows.append({"code": it["itemCode"], "name": name, "market": mkt})
            time.sleep(0.05)
    df = pd.DataFrame(rows).drop_duplicates("code")
    df["pref"] = ~df["code"].str.endswith("0")                 # 우선주(코드 끝자리 0 아님)
    if len(df) < 1500:
        raise RuntimeError(f"종목 목록 {len(df)}개뿐 — 네이버 응답 확인 필요")
    return df


# ── 2. 일봉 ──────────────────────────────────────────
ROW = re.compile(r'\["(\d{8})",\s*([\d.]+),\s*([\d.]+),\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\]')


def daily(code: str, start: str, end: str) -> pd.DataFrame | None:
    for attempt in range(3):
        try:
            r = requests.get("https://api.finance.naver.com/siseJson.naver",
                             params={"symbol": code, "requestType": 1, "timeframe": "day",
                                     "startTime": start, "endTime": end}, headers=UA, timeout=20)
            rows = ROW.findall(r.text)
            if rows:
                df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume", "fr"])
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date").replace("", np.nan).astype(float)
                df = df[df["close"] > 0]
                df.loc[df["open"] <= 0, "open"] = df["close"]
                return df
            return None
        except requests.RequestException:
            time.sleep(1 + attempt)
    return None


# ── 3. 특징 (모두 '전일까지' 데이터로 계산 → 미래 정보 없음) ─────────────
def rsi(c: pd.Series, n=14) -> float:
    d = c.diff().dropna().tail(n)
    up, dn = d.clip(lower=0).mean(), (-d.clip(upper=0)).mean()
    return float(100 - 100 / (1 + up / dn)) if dn > 0 else 100.0


def features(df: pd.DataFrame) -> dict:
    """df = 전일까지의 일봉(마지막 행 = 전일). 오늘 급등 '전'의 모습."""
    c, v, h, l, o = df["close"], df["volume"], df["high"], df["low"], df["open"]
    f = {}
    if len(df) < 25:
        return f
    last = c.iloc[-1]
    tv = c * v
    mid, sd = c.rolling(20).mean(), c.rolling(20).std(ddof=0)
    up, lo = mid + 2 * sd, mid - 2 * sd
    bw = (up - lo) / mid
    f["pctb"] = float((last - lo.iloc[-1]) / (up.iloc[-1] - lo.iloc[-1])) if up.iloc[-1] > lo.iloc[-1] else None
    f["bw"] = float(bw.iloc[-1])
    win = bw.tail(120).dropna()
    f["bw_pctile"] = float((win < bw.iloc[-1]).mean()) if len(win) > 20 else None   # 0 = 최근 6개월 중 가장 좁음
    f["squeeze"] = bool(f["bw_pctile"] is not None and f["bw_pctile"] <= 0.1)
    f["rsi14"] = rsi(c)
    for n in (5, 20, 60, 120):
        f[f"ma{n}_gap"] = float(last / c.tail(n).mean() - 1) if len(c) >= n else None   # 이평선 대비 이격
    ma = [c.tail(n).mean() for n in (5, 20, 60) if len(c) >= n]
    f["ma_aligned"] = bool(len(ma) == 3 and ma[0] > ma[1] > ma[2])                      # 정배열
    f["ret5"] = float(last / c.iloc[-6] - 1) if len(c) > 5 else None
    f["ret20"] = float(last / c.iloc[-21] - 1) if len(c) > 20 else None
    f["ret60"] = float(last / c.iloc[-61] - 1) if len(c) > 60 else None
    hi = h.tail(250).max()
    f["from_high"] = float(last / hi - 1)                                                # 52주(가용 기간) 고점 대비
    f["from_low"] = float(last / l.tail(250).min() - 1)
    f["vol_ratio_prev"] = float(v.iloc[-1] / v.iloc[-21:-1].mean()) if v.iloc[-21:-1].mean() > 0 else None
    f["tv20_avg"] = float(tv.tail(20).mean())
    f["tv_prev"] = float(tv.iloc[-1])
    f["prev_chg"] = float(last / c.iloc[-2] - 1)
    f["up_days"] = int((c.diff().tail(10)[::-1] > 0).cumprod().sum())                    # 연속 상승일
    rng = (h.iloc[-1] - l.iloc[-1])
    f["prev_close_pos"] = float((last - l.iloc[-1]) / rng) if rng > 0 else None          # 전일 종가가 고저 범위 어디
    f["fr"] = float(df["fr"].iloc[-1]) if "fr" in df and pd.notna(df["fr"].iloc[-1]) else None   # 외국인 소진율
    f["price"] = float(last)
    return f


def today_bar(df: pd.DataFrame) -> dict:
    """오늘 봉(급등 당일) 모양"""
    t, p = df.iloc[-1], df.iloc[-2]
    rng = t["high"] - t["low"]
    body_top = max(t["open"], t["close"])
    return {"chg": float(t["close"] / p["close"] - 1) * 100,
            "gap": float(t["open"] / p["close"] - 1) * 100,                      # 시가 갭
            "high_chg": float(t["high"] / p["close"] - 1) * 100,                 # 장중 최고 상승률
            "close_pos": float((t["close"] - t["low"]) / rng) if rng > 0 else 1.0,   # 1 = 고가 마감
            "upper_wick": float((t["high"] - body_top) / p["close"]) * 100,
            "limit_up": bool(t["close"] / p["close"] - 1 >= 0.295),
            "tv": float(t["close"] * t["volume"]),
            "vol_ratio": float(t["volume"] / df["volume"].iloc[-21:-1].mean()) if df["volume"].iloc[-21:-1].mean() > 0 else None,
            "close": float(t["close"])}


# ── 4. DART 공시 ─────────────────────────────────────
CATALYST_DART = [
    ("실적", r"영업\(잠정\)실적|잠정실적|매출액또는손익구조|손익구조"),
    ("수주·계약", r"공급계약|판매ㆍ공급|판매·공급|수주"),
    ("임상·허가", r"임상|품목허가|허가|기술이전|라이선스"),
    ("자사주·소각", r"자기주식취득|주식소각|자사주"),
    ("무상증자·분할", r"무상증자|주식분할|액면분할"),
    ("유상증자·CB", r"유상증자|전환사채|신주인수권부사채|교환사채"),
    ("M&A·지배구조", r"합병|인수|공개매수|최대주주|경영권|타법인주식|영업양수|분할"),
    ("투자·시설", r"신규시설|투자판단|유형자산"),
    ("특허", r"특허"),
    ("거래소 조치", r"조회공시|투자경고|투자주의|단기과열|매매거래정지"),
]


def dart_filings(key: str, days: list[str]) -> dict[str, list[dict]]:
    """여러 날의 전체 공시 → {종목코드: [공시]}"""
    out: dict[str, list[dict]] = {}
    for d in days:
        page = 1
        while page <= 40:
            j = requests.get("https://opendart.fss.or.kr/api/list.json", timeout=20, params={
                "crtfc_key": key, "bgn_de": d, "end_de": d, "page_no": page, "page_count": 100}).json()
            if j.get("status") != "000":
                break
            for it in j.get("list", []):
                sc = (it.get("stock_code") or "").strip()
                if sc:
                    out.setdefault(sc, []).append({"date": d, "title": re.sub(r"\s+", " ", it["report_nm"]).strip(),
                                                   "rcept_no": it["rcept_no"], "filer": it.get("flr_nm", "")})
            if page >= int(j.get("total_page", 1)):
                break
            page += 1
            time.sleep(0.1)
    return out


def classify(texts: list[str], rules) -> list[str]:
    tags = []
    for tag, pat in rules:
        if any(re.search(pat, t, re.I) for t in texts) and tag not in tags:
            tags.append(tag)
    return tags


# ── 5. 뉴스 (구글 뉴스 RSS — 제목만) ───────────────────
CATALYST_NEWS = [
    ("실적", r"실적|흑자|어닝|영업이익|매출 ?(급증|최대)|사상 ?최대"),
    ("수주·계약", r"수주|공급 ?계약|계약 ?체결|납품"),
    ("임상·허가", r"임상|FDA|허가|승인|기술이전|라이선스"),
    ("M&A·지배구조", r"인수|합병|M&A|매각|경영권|지분 ?취득"),
    ("정책·정부", r"정부|정책|규제|법안|국회|대통령|지원책|예산"),
    ("신기술·신제품", r"개발|신제품|출시|세계 ?최초|국산화|특허"),
    ("수급", r"외국인|기관|순매수|공매도"),
    ("상한가·급등", r"상한가|급등|강세"),
]
THEMES = ["AI", "반도체", "HBM", "2차전지", "배터리", "로봇", "원전", "방산", "조선", "바이오", "제약", "우주", "항공",
          "자율주행", "전기차", "수소", "태양광", "풍력", "게임", "엔터", "화장품", "식품", "건설", "철강", "금융", "보안",
          "양자", "초전도", "스테이블코인", "가상자산", "비트코인", "남북", "광통신", "데이터센터", "전력", "변압기", "의료기기"]


def news(name: str, n: int = 6) -> list[dict]:
    try:
        r = requests.get("https://news.google.com/rss/search", headers=UA, timeout=15,
                         params={"q": f'"{name}" when:2d', "hl": "ko", "gl": "KR", "ceid": "KR:ko"})
        root = ElementTree.fromstring(r.content)
        out = []
        for it in root.iter("item"):
            title = (it.findtext("title") or "").strip()
            src = it.find("source")
            out.append({"title": title, "source": src.text if src is not None else "",
                        "date": it.findtext("pubDate") or "", "link": it.findtext("link") or ""})
            if len(out) >= n:
                break
        return out
    except Exception:
        return []


def themes_of(texts: list[str]) -> list[str]:
    s = " ".join(texts)
    return [t for t in THEMES if t in s]


# ── 6. 이후 수익률 추적 ───────────────────────────────
def update_follow(surges: pd.DataFrame, closes: dict[str, pd.Series]) -> pd.DataFrame:
    if surges.empty:
        return surges
    for k in FOLLOW:
        col = f"ret_{k}d"
        if col not in surges:
            surges[col] = np.nan
    for i, r in surges.iterrows():
        s = closes.get(r["code"])
        if s is None:
            continue
        d0 = pd.Timestamp(r["date"])
        after = s[s.index > d0]
        for k in FOLLOW:
            col = f"ret_{k}d"
            if pd.isna(r.get(col)) and len(after) >= k:
                surges.at[i, col] = round((after.iloc[k - 1] / r["close"] - 1) * 100, 2)
    return surges


# ── 7. 리포트 그림 ───────────────────────────────────
def draw(top: list[dict], frames: dict[str, pd.DataFrame], path: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    from matplotlib.patches import Rectangle
    for fnt in ("NanumGothic", "Noto Sans CJK KR", "Noto Sans CJK JP"):
        if any(fnt == x.name for x in font_manager.fontManager.ttflist):
            plt.rcParams["font.family"] = fnt
            break
    plt.rcParams["axes.unicode_minus"] = False
    n = len(top)
    if not n:
        return
    cols = 2
    rows = (n + 1) // 2
    fig, axs = plt.subplots(rows, cols, figsize=(10, 2.8 * rows), facecolor="white")
    axs = np.atleast_1d(axs).ravel()
    for ax, s in zip(axs, top):
        df = frames[s["code"]].tail(60)
        c = frames[s["code"]]["close"]
        mid, sd = c.rolling(20).mean(), c.rolling(20).std(ddof=0)
        x = np.arange(len(df))
        ax.fill_between(x, (mid - 2 * sd).tail(60), (mid + 2 * sd).tail(60), color="#3B82F6", alpha=0.08)
        ax.plot(x, (mid + 2 * sd).tail(60).values, color="#3B82F6", lw=0.8)
        ax.plot(x, (mid - 2 * sd).tail(60).values, color="#3B82F6", lw=0.8)
        for i, (_, r) in enumerate(df.iterrows()):
            col = "#E5484D" if r["close"] >= r["open"] else "#3B82F6"
            ax.plot([i, i], [r["low"], r["high"]], color=col, lw=0.8)
            ax.add_patch(Rectangle((i - 0.3, min(r["open"], r["close"])), 0.6, max(abs(r["close"] - r["open"]), 1e-6), color=col))
        ax.set_title(f"{s['name']} +{s['chg']:.1f}% · {', '.join(s['catalysts'][:2]) or '재료 미확인'}", fontsize=9, loc="left")
        ax.set_xticks([]); ax.tick_params(labelsize=7)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    for ax in axs[n:]:
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


# ── 메인 ─────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--no-send", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    today = pd.Timestamp(a.date) if a.date else pd.Timestamp(dt.datetime.now(KST).date())
    tstr = f"{today:%Y-%m-%d}"
    os.makedirs(os.path.join(DATA, "universe"), exist_ok=True)
    os.makedirs(os.path.join(DATA, "daily"), exist_ok=True)
    os.makedirs(os.path.join(HERE, "reports", "img"), exist_ok=True)
    if os.path.exists(os.path.join(DATA, "daily", f"{tstr}.json")) and not a.date:
        print(f"{tstr} 이미 수집함 — 건너뜀"); return

    lst = listing()
    print("종목 수:", len(lst), flush=True)
    start = f"{today - pd.Timedelta(days=400):%Y%m%d}"
    end = f"{today:%Y%m%d}"
    frames: dict[str, pd.DataFrame] = {}
    with cf.ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(daily, c, start, end): c for c in lst["code"]}
        for i, fu in enumerate(cf.as_completed(futs)):
            df = fu.result()
            if df is not None and len(df) >= 25:
                frames[futs[fu]] = df
            if i % 500 == 0:
                print(f"일봉 {i}/{len(futs)}", flush=True)
    last_dates = pd.Series({c: df.index[-1] for c, df in frames.items()})
    if (last_dates == today).sum() < len(frames) * 0.5:
        print(f"{tstr} 봉이 대부분 없음 — 휴장일이거나 아직 장 마감 전. 종료"); return

    names = lst.set_index("code")
    uni, surgers = [], []
    for c, df in frames.items():
        if df.index[-1] != today or len(df) < 26:
            continue
        f = features(df.iloc[:-1])
        tb = today_bar(df)
        row = {"date": tstr, "code": c, "name": names.at[c, "name"], "market": names.at[c, "market"],
               "pref": bool(names.at[c, "pref"]), **{k: tb[k] for k in ("chg", "gap", "tv", "vol_ratio", "close")}, **f}
        big = bool((f.get("tv20_avg") or 0) >= BIG_TV)
        row["big"] = big
        row["surge"] = bool(tb["chg"] >= SURGE_PCT or (big and tb["chg"] >= BIG_PCT))
        uni.append(row)
        if row["surge"] and not row["pref"]:
            surgers.append({**row, **tb})
    U = pd.DataFrame(uni)
    U.to_csv(os.path.join(DATA, "universe", f"{tstr}.csv.gz"), index=False, compression="gzip", float_format="%.5g")
    print(f"전 종목 {len(U)} · 급등주 {len(surgers)}", flush=True)

    # 공시: 오늘 + 직전 영업일 (밤사이·전날 장 마감 후 공시가 재료인 경우가 많음)
    key = os.environ.get("DART_API_KEY", "").strip()
    prev_day = frames[next(iter(frames))].index
    prev_day = f"{prev_day[prev_day < today][-1]:%Y%m%d}" if (prev_day < today).any() else None
    filings = dart_filings(key, [d for d in (prev_day, f"{today:%Y%m%d}") if d]) if key else {}

    # 내일 급등 후보 10선 (규칙 점수 v0) + 어제 후보 채점 → data/candidates/
    try:
        import candidates
        cpath, cand = candidates.run(frames, names, filings, today, features, today_bar)
        print(f"급등 후보 {len(cand['candidates'])}개 저장: {cpath}", flush=True)
    except Exception as e:
        print("급등 후보 계산 실패:", type(e).__name__, e, flush=True)

    for s in surgers:
        fl = filings.get(s["code"], [])
        nw = news(s["name"])
        s["filings"] = fl[:10]
        s["news"] = nw
        dart_tags = classify([x["title"] for x in fl], CATALYST_DART)
        news_tags = classify([x["title"] for x in nw], CATALYST_NEWS)
        s["catalysts_dart"], s["catalysts_news"] = dart_tags, news_tags
        s["catalysts"] = list(dict.fromkeys([t for t in dart_tags if t != "거래소 조치"] +
                                            [t for t in news_tags if t != "상한가·급등"]))   # 결과 태그는 재료 아님
        s["themes"] = themes_of([x["title"] for x in nw] + [x["title"] for x in fl])
        time.sleep(0.3)
    surgers.sort(key=lambda s: (-(s["tv"] >= MIN_TV), -s["chg"]))

    # 시장 맥락
    ctx = {"n_stocks": int(len(U)), "n_up": int((U["chg"] > 0).sum()), "n_down": int((U["chg"] < 0).sum()),
           "n_surge": len(surgers), "n_limit_up": int(sum(s["limit_up"] for s in surgers)),
           "median_chg": float(U["chg"].median())}
    out = {"date": tstr, "context": ctx, "surgers": surgers}
    json.dump(out, open(os.path.join(DATA, "daily", f"{tstr}.json"), "w"), ensure_ascii=False, indent=1, default=float)

    # 누적 표 + 이후 수익률
    sp = os.path.join(DATA, "surges.csv")
    keep = ["date", "code", "name", "market", "chg", "gap", "high_chg", "close_pos", "upper_wick", "limit_up", "tv", "vol_ratio",
            "close", "pctb", "bw", "bw_pctile", "squeeze", "rsi14", "ma20_gap", "ma60_gap", "ma_aligned", "ret5", "ret20",
            "from_high", "vol_ratio_prev", "prev_chg", "up_days", "fr"]
    new = pd.DataFrame([{k: s.get(k) for k in keep} | {"catalysts": "|".join(s["catalysts"]), "themes": "|".join(s["themes"]),
                                                     "dart_n": len(s["filings"])} for s in surgers])
    S = pd.read_csv(sp, dtype={"code": str}) if os.path.exists(sp) else pd.DataFrame()
    S = pd.concat([S[S["date"] != tstr] if not S.empty else S, new], ignore_index=True)
    S = update_follow(S, {c: df["close"] for c, df in frames.items()})
    S.to_csv(sp, index=False, float_format="%.5g")

    # 리포트
    top = [s for s in surgers if s["tv"] >= MIN_TV][:8] or surgers[:8]
    img = os.path.join(HERE, "reports", "img", f"{tstr}.png")
    try:
        draw(top, frames, img)
    except Exception as e:
        print("그림 실패:", e)
    write_report(out, top, S, os.path.join(HERE, "reports", f"{tstr}.md"))
    if not a.no_send:
        send_summary(out, top)
    print("완료:", tstr)


def eok(x):
    return f"{x / 1e8:,.0f}억"


def write_report(out: dict, top: list[dict], S: pd.DataFrame, path: str):
    d, ctx, sur = out["date"], out["context"], out["surgers"]
    L = [f"# 급등주 리포트 · {d}", "",
         f"> 전 종목 {ctx['n_stocks']:,} · 상승 {ctx['n_up']:,} / 하락 {ctx['n_down']:,} · 중앙값 {ctx['median_chg']:+.2f}% · "
         f"**급등(+{SURGE_PCT:.0f}%↑) {ctx['n_surge']}종목**, 상한가 {ctx['n_limit_up']}", "",
         f"[목차](../README.md) · [분석 노트](../notes/{d}.md) · [패턴 정리](../PATTERNS.md)", ""]
    if os.path.exists(os.path.join(HERE, "reports", "img", f"{d}.png")):
        L += [f"![{d} 급등주](img/{d}.png)", ""]
    L += ["## 급등주 (거래대금 10억 이상 우선)", "",
          "| 종목 | 등락 | 갭 | 종가위치 | 거래대금 | 거래량배수 | 재료(자동) | 테마 |", "|---|--:|--:|--:|--:|--:|---|---|"]
    for s in sur[:30]:
        L.append(f"| {s['name']} | {s['chg']:+.1f}% | {s['gap']:+.1f}% | {s['close_pos']:.2f} | {eok(s['tv'])} | "
                 f"{(s['vol_ratio'] or 0):.1f}x | {', '.join(s['catalysts']) or '-'} | {', '.join(s['themes'][:3]) or '-'} |")
    L += ["", "## 급등 전날의 모습 (상위 종목)", "",
          "| 종목 | %b | 밴드폭 하위% | 스퀴즈 | RSI | 20일선 이격 | 정배열 | 20일 수익률 | 고점 대비 | 전일 거래량배수 |",
          "|---|--:|--:|:-:|--:|--:|:-:|--:|--:|--:|"]
    pct = lambda v: "-" if v is None or v != v else f"{v * 100:+.1f}%"
    for s in top:
        L.append(f"| {s['name']} | {s.get('pctb') or 0:.2f} | {(s.get('bw_pctile') or 0) * 100:.0f} | {'✓' if s.get('squeeze') else ''} | "
                 f"{s.get('rsi14') or 0:.0f} | {pct(s.get('ma20_gap'))} | {'✓' if s.get('ma_aligned') else ''} | {pct(s.get('ret20'))} | "
                 f"{pct(s.get('from_high'))} | {(s.get('vol_ratio_prev') or 0):.1f}x |")
    L += ["", "## 공시·뉴스 (상위 종목)", ""]
    for s in top:
        L += [f"### {s['name']} ({s['code']}) {s['chg']:+.1f}%", ""]
        for f in s["filings"][:5]:
            L.append(f"- 📄 [{f['title']}](https://dart.fss.or.kr/dsaf001/main.do?rcpNo={f['rcept_no']}) · {f['date']}")
        for n in s["news"][:4]:
            L.append(f"- 📰 {n['title']}")
        if not s["filings"] and not s["news"]:
            L.append("- 공시·뉴스 없음 → 테마·수급성 움직임일 가능성")
        L.append("")
    if not S.empty and "ret_5d" in S:
        done = S.dropna(subset=["ret_5d"])
        if len(done) >= 5:
            L += ["## 누적 통계 — 급등 다음에 무슨 일이?", "",
                  f"- 표본 {len(done)}건 · 5거래일 뒤 평균 {done['ret_5d'].mean():+.1f}% · 중앙값 {done['ret_5d'].median():+.1f}% · "
                  f"플러스 비율 {(done['ret_5d'] > 0).mean() * 100:.0f}%", ""]
    L += ["---", "", "※ 재료는 공시 제목·뉴스 제목 키워드로 자동 분류한 것입니다. 판단은 [분석 노트](../notes/) 참고. 투자 권유 아님.", ""]
    open(path, "w", encoding="utf-8").write("\n".join(L))


def send_summary(out: dict, top: list[dict]):
    tok = (os.environ.get("TELEGRAM_TOKEN") or "").strip()
    chat = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    if not tok or not chat:
        print("텔레그램 미설정 — 건너뜀"); return
    if chat.startswith("-"):
        print("그룹방으로는 보내지 않음"); return
    ctx = out["context"]
    L = [f"🚀 <b>급등주 {out['date']}</b> — +{SURGE_PCT:.0f}%↑ {ctx['n_surge']}종목 · 상한가 {ctx['n_limit_up']}",
         f"상승 {ctx['n_up']:,} / 하락 {ctx['n_down']:,} · 중앙값 {ctx['median_chg']:+.2f}%", ""]
    for s in top[:8]:
        tag = ", ".join(s["catalysts"][:2]) or "재료 미확인"
        L.append(f"• <b>{html.escape(s['name'])}</b> {s['chg']:+.1f}% · {eok(s['tv'])} · {html.escape(tag)}")
    L += ["", f"<a href=\"{REPO_URL}/reports/{out['date']}.md\">리포트(차트·공시·뉴스)</a>"]
    requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", timeout=20,
                  data={"chat_id": chat, "text": "\n".join(L), "parse_mode": "HTML", "disable_web_page_preview": "true"})


if __name__ == "__main__":
    main()
