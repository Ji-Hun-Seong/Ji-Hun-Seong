"""장중 급등주 재료 미리 수집 — 스냅샷 직후 GitHub Actions에서 실행 (노트 작성 때 웹 검색을 안 해도 되게)

  python surge-study/intraday_news.py us    # 미국: 구글 뉴스 영어 제목 + SEC 공시(8-K 항목)
  python surge-study/intraday_news.py kr    # 한국: 구글 뉴스 한국어 제목 + DART 오늘 공시

오늘 스냅샷(data/intraday/{mkt}/날짜.csv)의 마지막 시각에서 +10%↑(미국은 $2↑·시총 $3억↑) 종목 중
아직 안 모은 종목만 동시에(병렬) 가져와 data/intraday/{mkt}/news-날짜.csv 에 이어 붙인다.
열: symbol, fetched_at, auto_cat(키워드 자동 분류), themes, headlines(신뢰도 순 5개 ' || ', ★=신뢰 매체), filings, link
환경변수(있으면 사용): SEC_UA(미국 SEC), DART_API_KEY(한국 DART)
"""
from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import os
import re
import sys
from zoneinfo import ZoneInfo

import pandas as pd
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from collect import CATALYST_DART, CATALYST_NEWS, classify, news, themes_of  # noqa: E402
from us_collect import CATALYST_US, news_en, sec_filings, sec_map  # noqa: E402

TZ = {"us": "America/New_York", "kr": "Asia/Seoul"}
COLS = ["symbol", "fetched_at", "auto_cat", "themes", "headlines", "filings", "link"]
US_THEMES = ["AI", "chip", "semiconductor", "data center", "nuclear", "solar", "bitcoin", "crypto", "quantum", "drone",
             "defense", "robot", "EV", "battery", "biotech", "uranium", "gold", "silver", "cloud", "optical"]


def targets(mkt: str, day: str, done: set[str]) -> pd.DataFrame:
    p = os.path.join(HERE, "data", "intraday", mkt, f"{day}.csv")
    if not os.path.exists(p):
        return pd.DataFrame()
    df = pd.read_csv(p, dtype={"code": str})
    df = df[df["time"] == df["time"].max()]
    df = df[df["chg"] >= 10]
    if mkt == "us":
        df = df[(df["price"] >= 2) & (df["mcap"].fillna(0) >= 3e8)].rename(columns={"symbol": "sym"})
    else:
        df = df.rename(columns={"code": "sym"})
    return df[~df["sym"].astype(str).isin(done)]


def dart_today(key: str, day: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for page in range(1, 31):
        try:
            j = requests.get("https://opendart.fss.or.kr/api/list.json", timeout=15, params={
                "crtfc_key": key, "bgn_de": day.replace("-", ""), "end_de": day.replace("-", ""),
                "page_no": page, "page_count": 100}).json()
        except Exception:
            break
        if j.get("status") != "000":
            break
        for it in j.get("list", []):
            sc = (it.get("stock_code") or "").strip()
            if sc:
                out.setdefault(sc, []).append(re.sub(r"\s+", " ", it["report_nm"]).strip())
        if page >= int(j.get("total_page", 1)):
            break
    return out


def one_us(r, tick, ua, since) -> dict:
    sym = r["sym"]
    nw = news_en(sym, r.get("name", ""), n=5)
    fl = sec_filings(tick[sym.upper()], ua, since) if ua and sym.upper() in tick else []
    texts = [x["title"] for x in nw]
    cats = classify(texts, CATALYST_US)
    if any("2.02" in x["items"] for x in fl) and "Earnings" not in cats:
        cats.insert(0, "Earnings")
    if any("1.01" in x["items"] for x in fl) and "Contract·Partnership" not in cats:
        cats.append("Contract·Partnership")
    s = " ".join(texts)
    th = [t for t in US_THEMES if re.search(rf"\b{re.escape(t)}\b", s, 0 if t in ("AI", "EV") else re.I)]
    return {"symbol": sym, "auto_cat": "/".join(cats), "themes": "/".join(th),
            "headlines": " || ".join(texts),
            "filings": " || ".join(f"{x['date']} {x['form']} {x['items_kr']}".strip() for x in fl[:4]),
            "link": fl[0]["url"] if fl else ""}


def one_kr(r, dart) -> dict:
    code, name = str(r["sym"]), r["name"]
    nw = news(name, n=5, extra=("특징주", "주가"))                 # 신뢰도 순 상위 5개
    texts = [x["title"] for x in nw]
    shown = [("★" if x.get("tier") == "A" else "") + x["title"] for x in nw]   # ★ = 신뢰 매체
    fl = dart.get(code, [])
    cats = classify(fl, CATALYST_DART) + [c for c in classify(texts, CATALYST_NEWS)]
    cats = list(dict.fromkeys(cats))
    return {"symbol": code, "auto_cat": "/".join(cats), "themes": "/".join(themes_of(texts + fl)),
            "headlines": " || ".join(shown), "filings": " || ".join(fl[:4]), "link": nw[0]["link"] if nw else ""}


def main(mkt: str):
    now = dt.datetime.now(ZoneInfo(TZ[mkt]))
    day = now.strftime("%Y-%m-%d")
    out_p = os.path.join(HERE, "data", "intraday", mkt, f"news-{day}.csv")
    done = set(pd.read_csv(out_p, dtype=str)["symbol"]) if os.path.exists(out_p) else set()
    tg = targets(mkt, day, done)
    if tg.empty:
        print(f"{mkt} 뉴스: 새 +10% 종목 없음"); return
    rows = [r for _, r in tg.iterrows()]
    if mkt == "us":
        ua = os.environ.get("SEC_UA", "").strip()
        tick = sec_map(ua) if ua else {}
        since = (now.date() - dt.timedelta(days=3)).isoformat()
        job = lambda r: one_us(r, tick, ua, since)          # noqa: E731
    else:
        key = os.environ.get("DART_API_KEY", "").strip()
        dart = dart_today(key, day) if key else {}
        job = lambda r: one_kr(r, dart)                     # noqa: E731
    with cf.ThreadPoolExecutor(8) as ex:                    # 종목별 요청을 동시에 → 20종목도 몇 초
        res = list(ex.map(job, rows))
    for x in res:
        x["fetched_at"] = now.strftime("%H:%M")
    pd.DataFrame(res, columns=COLS).to_csv(out_p, mode="a", header=not os.path.exists(out_p), index=False)
    print(f"{mkt} 뉴스: {len(res)}종목 저장 · 자동분류 있음 {sum(bool(x['auto_cat']) for x in res)}")


if __name__ == "__main__":
    main((sys.argv[1:] or ["us"])[0])
