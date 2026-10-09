import sys
import numpy as np, pandas as pd
sys.path.insert(0, ".")
import engine
from engine import *
piv, idx = load("/tmp/claude-0/btkr/kospi_all.csv.gz", "KPI200")
keep = [c for c in piv["Close"].columns if c.endswith("0")]          # 보통주만
piv = {k: v[keep] for k, v in piv.items()}
f = features(piv, idx); C = f["C"]
age = C.notna().cumsum()
tv = f["tv"].where(age > 250)
me = tv.resample("ME").last()                                          # 월말 거래대금 순위 → 다음 달 유니버스
rank = me.rank(axis=1, ascending=False)
uni = (rank <= 200).shift(1).reindex(C.index, method="ffill").fillna(False).astype(bool)
print("유니버스 평균 종목 수", uni.loc[START:].sum(axis=1).mean().round(0))
mom_r = f["mom"].where(uni).rank(axis=1, pct=True)
up = C > f["ma200"]; sq = f["bw_q"].rolling(5).min() < 0.2
S = {
 "S0 BB하단+RSI14<30":  dict(entry=(C < f["lo"]) & (f["rsi14"] < 30) & up, score=f["rsi14"], exit_sig=(C >= f["mid"]) | (f["rsi14"] >= 55), max_pos=10, hold=10, stop=0.08),
 "S1 RSI2+%b":          dict(entry=(f["rsi2"] < 10) & (f["pb"] < 0.2) & up, score=f["rsi2"], exit_sig=(C > f["ma5"]) | (f["rsi2"] > 70), max_pos=10, hold=10),
 "S2 주도주 눌림목":      dict(entry=(mom_r > 0.7) & up & (f["pb"] < 0.2) & (f["rsi3"] < 20), score=f["mom"], ascending=False, exit_sig=(f["rsi3"] > 80) | (f["pb"] > 0.9), max_pos=10, hold=15),
 "S3 스퀴즈 돌파":        dict(entry=sq & (C > f["up"]) & (f["rsi14"] > 60) & (f["ma50"] > f["ma200"]), score=f["mom"], ascending=False, exit_sig=f["rsi14"] < 40, max_pos=15, hold=250),
 "S4 모멘텀+완만한 눌림":   dict(entry=(mom_r > 0.8) & up & (f["pb"] < 0.4) & (f["rsi14"] < 50), score=f["mom"], ascending=False, exit_sig=(f["rsi14"] > 75) | (C < f["ma200"]), max_pos=10, hold=60),
}
def line(name, opt, m):
    a, i, o = m["ALL"], m["IS"], m["OOS"]
    print(f"{name:18s} {opt:8s} | {a['CAGR']:+.1%} {a['MDD']:+.1%} Sh{a['Sharpe']:.2f} 노출{a.get('Expo',1):.0%} | IS {i['CAGR']:+.1%} Sh{i['Sharpe']:.2f} MDD{i['MDD']:+.1%} | OOS {o['CAGR']:+.1%} Sh{o['Sharpe']:.2f} MDD{o['MDD']:+.1%} | N{a.get('N',0)} W{a.get('Win',0):.0%} {a.get('AvgTr',0):+.2%} {a.get('Days',0):.0f}d", flush=True)
bench = idx[idx.index >= START]
line("코스피200 지수", "", split_metrics(bench, pd.Series(1.0, index=bench.index)))
r = C.pct_change(fill_method=None)
ew = r.where(uni.shift(1).fillna(False)).mean(axis=1).loc[START:].fillna(0)
line("동일비중(시점별200)", "", split_metrics((1 + ew).cumprod(), pd.Series(1.0, index=ew.index)))
for name, kw in S.items():
    for regime, park in [(True, False), (True, True)]:
        k = dict(kw); k["entry"] = k["entry"] & uni
        eq, ex, tr = simulate(f, regime=regime, park=park, **k)
        line(name, f"{'R' if regime else '-'}{'P' if park else '-'}", split_metrics(eq, ex, tr))
import pickle; pickle.dump((uni, mom_r), open("kr_pit.pkl", "wb"))
