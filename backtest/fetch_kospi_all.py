"""fetch_kospi_all.py — 코스피 상장 전 종목(보통주) 일봉을 받아 backtest/data/kospi_all.csv.gz 로 저장.
코스피200 '현재' 구성종목만 쓰면 생기는 선정 편향을 줄이려고, 시점별 거래대금 상위로 유니버스를 다시 만드는 데 쓴다."""
import os
import time

import pandas as pd
import requests

from backtest import UA, prices

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "data")
os.makedirs(D, exist_ok=True)

codes = {}
for page in range(1, 40):
    r = requests.get("https://m.stock.naver.com/api/stocks/marketValue/KOSPI",
                     params={"page": page, "pageSize": 100}, headers=UA, timeout=20)
    j = r.json()
    items = j.get("stocks", []) if isinstance(j, dict) else j
    if page == 1:
        print("listing sample:", str(j)[:300])
    if not items:
        break
    for it in items:
        if it.get("stockEndType") == "stock":
            codes[it["itemCode"]] = it.get("stockName", "")
    time.sleep(0.1)
print("KOSPI stocks:", len(codes))
pd.Series(codes, name="name").rename_axis("code").to_csv(os.path.join(D, "kospi_all_members.csv"), encoding="utf-8-sig")

frames = []
for i, c in enumerate(codes):
    try:
        frames.append(prices(c, "2014-01-01").assign(code=c))
    except Exception as e:
        print("skip", c, e)
    time.sleep(0.1)
    if i % 100 == 0:
        print(i, flush=True)
frames.append(prices("KPI200", "2014-01-01").assign(code="KPI200"))
allp = pd.concat(frames).reset_index().rename(columns={"index": "Date"})
allp.to_csv(os.path.join(D, "kospi_all.csv.gz"), index=False, compression="gzip", float_format="%.4f")
print(len(frames), "series", len(allp), "rows")
