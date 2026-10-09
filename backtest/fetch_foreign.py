"""fetch_foreign.py — 코스피 전 종목의 일별 외국인 보유율(네이버 '외국인소진율')을 받아
backtest/data/kospi_foreign.csv.gz 로 저장. 변화량이 곧 외국인 순매수(발행주식 대비 %p)다."""
import os
import re
import time
from datetime import date

import pandas as pd
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "data")
os.makedirs(D, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36"}

codes = {}
for page in range(1, 40):
    j = requests.get("https://m.stock.naver.com/api/stocks/marketValue/KOSPI",
                     params={"page": page, "pageSize": 100}, headers=UA, timeout=20).json()
    items = j.get("stocks", []) if isinstance(j, dict) else j
    if not items:
        break
    for it in items:
        if it.get("stockEndType") == "stock" and it["itemCode"].endswith("0"):
            codes[it["itemCode"]] = it.get("stockName", "")
    time.sleep(0.1)
print("KOSPI 보통주:", len(codes))

rows = []
for i, c in enumerate(codes):
    try:
        r = requests.get("https://api.finance.naver.com/siseJson.naver",
                         params={"symbol": c, "requestType": 1, "timeframe": "day",
                                 "startTime": "20140101", "endTime": date.today().strftime("%Y%m%d")},
                         headers=UA, timeout=30)
        for d, fr in re.findall(r'\["(\d{8})",\s*[\d.]+,\s*[\d.]+,\s*[\d.]+,\s*[\d.]+,\s*[\d.]+,\s*([\d.]+)\]', r.text):
            rows.append((d, c, float(fr)))
    except Exception as e:
        print("skip", c, e)
    time.sleep(0.08)
    if i % 100 == 0:
        print(i, len(rows), flush=True)
df = pd.DataFrame(rows, columns=["Date", "code", "FR"])
df.to_csv(os.path.join(D, "kospi_foreign.csv.gz"), index=False, compression="gzip")
print(df["code"].nunique(), "series", len(df), "rows", df["Date"].min(), df["Date"].max())
