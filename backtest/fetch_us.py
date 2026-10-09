"""fetch_us.py — S&P500 현재 구성종목 + SPY 일봉(수정주가)을 받아 backtest/data/us_prices.csv.gz 로 저장."""
import io
import os

import pandas as pd
import requests
import yfinance as yf

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "data")
os.makedirs(D, exist_ok=True)

html = requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
                    headers={"User-Agent": "Mozilla/5.0 backtest"}, timeout=30).text
tables = pd.read_html(io.StringIO(html))
print("tables:", [(i, t.shape, list(t.columns)[:6]) for i, t in enumerate(tables)])
members = tables[0]
members["yf"] = members["Symbol"].str.replace(".", "-", regex=False)
members.to_csv(os.path.join(D, "us_members.csv"), index=False)
# 시점별 구성종목 이력: github.com/fja05680/sp500 의 "S&P 500 Historical Components & Changes" CSV
api = requests.get("https://api.github.com/repos/fja05680/sp500/contents/", timeout=30).json()
names = sorted(x["name"] for x in api if x["name"].startswith("S&P 500 Historical Components") and x["name"].endswith(".csv"))
print("history files:", names[-3:])
dl = next(x["download_url"] for x in api if x["name"] == names[-1])
hist = pd.read_csv(io.StringIO(requests.get(dl, timeout=60).text))
hist["date"] = pd.to_datetime(hist["date"])
hist = hist[hist["date"] >= "2013-06-01"]
hist.to_csv(os.path.join(D, "us_hist.csv"), index=False)
ever = set()
for t in hist["tickers"]:
    ever |= {x.strip().replace(".", "-") for x in t.split(",")}
print("tickers ever in S&P500 since 2013-06:", len(ever), "last hist date", hist["date"].max())
tickers = sorted(set(members["yf"]) | ever) + ["SPY"]
print(len(tickers), "tickers")

px = yf.download(tickers, start="2014-01-01", auto_adjust=True, group_by="column", threads=True, progress=False)
frames = []
for f in ["Open", "High", "Low", "Close", "Volume"]:
    s = px[f].stack().rename(f)
    frames.append(s)
out = pd.concat(frames, axis=1).reset_index()
out.columns = ["Date", "code", "Open", "High", "Low", "Close", "Volume"]
out = out.dropna(subset=["Close"])
out.to_csv(os.path.join(D, "us_prices.csv.gz"), index=False, compression="gzip", float_format="%.4f")
print(out["code"].nunique(), "series", len(out), "rows", out["Date"].min(), out["Date"].max())
