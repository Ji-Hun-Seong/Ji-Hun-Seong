"""us_peers.py — 코스피 대형주마다 '밤사이 같이 움직이는' 미국 S&P500 종목 3개 찾기 → surge-study/data/us_peers.json

한국 날짜 d의 수익률(전일 종가→당일 종가)과 'd 이전 마지막 미국 거래일' 수익률의 상관이 가장 높은 3종목.
백테스트(largecap_backtest.md 2라운드): 2015~2021로 고른 동종 3사가 2022~2026에도 다음 날 수익을 잘 설명함.

  python surge-study/research/us_peers.py kospi_all.csv.gz us_prices.csv.gz kospi_all_members.csv [시작일]
"""
import json, os, sys
import numpy as np, pandas as pd

kr_path, us_path, mem_path = sys.argv[1:4]
start = sys.argv[4] if len(sys.argv) > 4 else "2018-01-01"
p = pd.read_csv(kr_path, dtype={"code": str}, parse_dates=["Date"]).rename(columns=str.lower).sort_values(["code", "date"])
p["tv"] = p["close"] * p["volume"]
p["chg"] = p.groupby("code")["close"].pct_change() * 100
p["tv20"] = p.groupby("code")["tv"].transform(lambda s: s.rolling(20).mean())
p = p[p["date"] >= start]
big = p[p["tv20"] >= 300e8]["code"].value_counts()
codes = big[big >= 120].index                                    # 최근 대형주였던 기간이 반년 이상
R = p[p["code"].isin(codes)].pivot(index="date", columns="code", values="chg")
us = pd.read_csv(us_path, parse_dates=["Date"]).sort_values(["code", "Date"])
us["r"] = us.groupby("code")["Close"].pct_change() * 100
U = us.pivot(index="Date", columns="code", values="r")
U = U.loc[U.index >= start]
U = U.loc[:, U.notna().mean() > 0.9]
pos = U.index.searchsorted(R.index, side="left") - 1
Ua = pd.DataFrame(U.values[np.clip(pos, 0, None)], index=R.index, columns=U.columns)
Uz = (Ua - Ua.mean()) / Ua.std()
names = pd.read_csv(mem_path, dtype={"code": str}).set_index("code")["name"].to_dict()
out = {}
for c in codes:
    y = R[c]; ok = y.notna() & Uz.notna().all(axis=1)
    if ok.sum() < 200:
        continue
    yz = (y[ok] - y[ok].mean()) / y[ok].std()
    cor = Uz[ok].mul(yz, axis=0).mean().sort_values(ascending=False)
    top = cor.head(3)
    out[c] = {"name": names.get(c, c), "peers": list(top.index), "corr": [round(float(v), 3) for v in top.values]}
dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "us_peers.json")
json.dump({"made": pd.Timestamp.today().strftime("%Y-%m-%d"), "from": start, "stocks": out}, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(out), "종목 →", dst)
for c in ("006400", "005930", "000660", "005380", "373220"):
    print(c, out.get(c))
