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
members = pd.read_html(io.StringIO(html))[0]
members["yf"] = members["Symbol"].str.replace(".", "-", regex=False)
members[["Symbol", "Security", "GICS Sector", "yf"]].to_csv(os.path.join(D, "us_members.csv"), index=False)
tickers = list(members["yf"]) + ["SPY"]
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
