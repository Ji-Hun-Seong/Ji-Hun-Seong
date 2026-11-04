"""장중 스냅샷 — 20분마다 상승률 상위 종목을 시각과 함께 기록 (급등이 '언제' 시작되는지 보기 위해)

  python surge-study/intraday.py kr     # 한국: 네이버 상승률 순위 (코스피·코스닥)
  python surge-study/intraday.py us     # 미국: 야후 Day Gainers

저장: surge-study/data/intraday/{kr|us}/YYYY-MM-DD.csv (장중 계속 이어 붙임, 날짜는 각 시장 현지 기준)
"""
from __future__ import annotations

import datetime as dt
import os
import re
import sys
from zoneinfo import ZoneInfo

import pandas as pd
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36"}
def num(s) -> float:
    try:
        return float(str(s).replace(",", ""))
    except (TypeError, ValueError):          # "-", "N/A", None 등
        return float("nan")


def kr() -> tuple[str, pd.DataFrame]:
    now = dt.datetime.now(ZoneInfo("Asia/Seoul"))
    if now.weekday() >= 5 or not ((9, 0) <= (now.hour, now.minute) <= (15, 45)):
        return "", pd.DataFrame()
    rows = []
    for mkt in ("KOSPI", "KOSDAQ"):
        for page in ((1, 2, 3) if mkt == "KOSPI" else (1, 2)):     # 코스피는 300위까지 (대형주 +3~5%도 잡히게)
            j = requests.get(f"https://m.stock.naver.com/api/stocks/up/{mkt}", params={"page": page, "pageSize": 100},
                             headers=UA, timeout=20).json()
            for it in j.get("stocks", []):
                name = it.get("stockName", "")
                if it.get("stockEndType") != "stock" or "스팩" in name or re.search(r"\d+호$", name):
                    continue
                rows.append({"time": now.strftime("%H:%M"), "code": it["itemCode"], "name": name, "market": mkt,
                             "price": num(it.get("closePrice")), "chg": num(it.get("fluctuationsRatio")),
                             "tv_eok": round(num(it.get("accumulatedTradingValue")) / 100, 1),   # 백만원 → 억원
                             "mcap_eok": num(it.get("marketValue")),
                             "limit_up": (it.get("compareToPreviousPrice") or {}).get("name") == "UPPER_LIMIT",
                             "traded_at": it.get("localTradedAt", "")})
    df = pd.DataFrame(rows)
    if df.empty:
        return "", df
    big = df["mcap_eok"] >= 50000                                       # 시총 5조↑ 대형주는 +3%부터 기록 (대형주의 호재성 움직임)
    df = df[(df["chg"] >= 5) | (big & (df["chg"] >= 3))].sort_values("chg", ascending=False)   # 급등 '진행 중' 포착
    return now.strftime("%Y-%m-%d"), df


def us() -> tuple[str, pd.DataFrame]:
    now = dt.datetime.now(ZoneInfo("America/New_York"))
    if now.weekday() >= 5 or not ((9, 30) <= (now.hour, now.minute) <= (16, 15)):
        return "", pd.DataFrame()
    j = requests.get("https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved", headers=UA, timeout=20,
                     params={"scrIds": "day_gainers", "count": 100, "formatted": "false"}).json()
    q = j["finance"]["result"][0]["quotes"]
    rows = [{"time": now.strftime("%H:%M"), "symbol": x.get("symbol"), "name": x.get("shortName") or x.get("longName", ""),
             "exchange": x.get("fullExchangeName", ""), "price": x.get("regularMarketPrice"),
             "chg": x.get("regularMarketChangePercent"), "volume": x.get("regularMarketVolume"),
             "avg_vol_3m": x.get("averageDailyVolume3Month"), "mcap": x.get("marketCap")} for x in q]
    df = pd.DataFrame(rows)
    if df.empty:
        return "", df
    df["vol_ratio"] = (df["volume"] / df["avg_vol_3m"]).round(2)
    return now.strftime("%Y-%m-%d"), df.sort_values("chg", ascending=False)


if __name__ == "__main__":
    mkt = (sys.argv[1:] or ["kr"])[0]
    day, df = (kr if mkt == "kr" else us)()
    if df.empty:
        print(f"{mkt}: 장 시간이 아니거나 데이터 없음 — 건너뜀"); sys.exit(0)
    d = os.path.join(HERE, "data", "intraday", mkt)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"{day}.csv")
    df.to_csv(p, mode="a", header=not os.path.exists(p), index=False)
    print(f"{mkt} {day} {df['time'].iloc[0]} · {len(df)}종목 기록 · 1위 {df.iloc[0]['name']} {df.iloc[0]['chg']:+.1f}%")
