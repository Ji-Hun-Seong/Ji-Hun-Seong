import sys
import numpy as np, pandas as pd
sys.path.insert(0, ".")
import engine
from engine import *
engine.BUY_COST = 0.0015; engine.SELL_COST = 0.0015; engine.PARK_COST = 0.0005
piv, idx = load("/tmp/claude-0/bt/us_prices.csv.gz", "SPY")
f = features(piv, idx); C = f["C"]
hist = pd.read_csv("/tmp/claude-0/bt/us_hist.csv", parse_dates=["date"]).sort_values("date")
rows = []
for d, t in zip(hist["date"], hist["tickers"]):
    s = {x.strip().replace(".", "-") for x in t.split(",")}
    rows.append(pd.Series(C.columns.isin(list(s)), index=C.columns, name=d))
mem = pd.DataFrame(rows)
mem = mem[~mem.index.duplicated(keep="last")].reindex(C.index, method="ffill").fillna(False).astype(bool)
cur = pd.read_csv("/tmp/claude-0/bt/us_members.csv")["yf"]
CUR = pd.DataFrame(np.repeat(C.columns.isin(cur).reshape(1, -1), len(C), 0), index=C.index, columns=C.columns)
up = C > f["ma200"]; sq = f["bw_q"].rolling(5).min() < 0.2
# 모멘텀 순위는 '그 시점 구성종목' 안에서 다시 계산
mom_pit = f["mom"].where(mem); mom_rank_pit = mom_pit.rank(axis=1, pct=True)
def S(mr):
    return {
 "S0 BB하단+RSI14<30":    dict(entry=(C < f["lo"]) & (f["rsi14"] < 30) & up, score=f["rsi14"], exit_sig=(C >= f["mid"]) | (f["rsi14"] >= 55), max_pos=10, hold=10, stop=0.08),
 "S2 주도주 눌림목":        dict(entry=(mr > 0.7) & up & (f["pb"] < 0.2) & (f["rsi3"] < 20), score=f["mom"], ascending=False, exit_sig=(f["rsi3"] > 80) | (f["pb"] > 0.9), max_pos=10, hold=15),
 "S3 스퀴즈 돌파":          dict(entry=sq & (C > f["up"]) & (f["rsi14"] > 60) & (f["ma50"] > f["ma200"]), score=f["mom"], ascending=False, exit_sig=f["rsi14"] < 40, max_pos=15, hold=250),
 "S4 모멘텀+완만한 눌림":     dict(entry=(mr > 0.8) & up & (f["pb"] < 0.4) & (f["rsi14"] < 50), score=f["mom"], ascending=False, exit_sig=(f["rsi14"] > 75) | (C < f["ma200"]), max_pos=10, hold=60),
}
def line(name, opt, m):
    a, i, o = m["ALL"], m["IS"], m["OOS"]
    print(f"{name:20s} {opt:10s} | {a['CAGR']:+.1%} {a['MDD']:+.1%} Sh{a['Sharpe']:.2f} 노출{a.get('Expo',1):.0%} | IS {i['CAGR']:+.1%} Sh{i['Sharpe']:.2f} MDD{i['MDD']:+.1%} | OOS {o['CAGR']:+.1%} Sh{o['Sharpe']:.2f} MDD{o['MDD']:+.1%} | N{a.get('N',0)} W{a.get('Win',0):.0%} {a.get('AvgTr',0):+.2%} {a.get('Days',0):.0f}d", flush=True)
bench = idx[idx.index >= START]
