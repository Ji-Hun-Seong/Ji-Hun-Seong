import sys, pickle
import numpy as np, pandas as pd
sys.path.insert(0, ".")
import engine
from engine import *
piv, idx = load("/tmp/claude-0/btkr/kospi_all.csv.gz", "KPI200")
C, O, V = piv["Close"], piv["Open"], piv["Volume"]
prefs = [c for c in C.columns if not c.endswith("0") and (c[:5] + "0") in C.columns]
P = C[prefs]; Cm = C[[p[:5] + "0" for p in prefs]].set_axis(prefs, axis=1)
Rr = np.log(P / Cm); rsiR = Rr.apply(lambda s: rsi(np.exp(s), 14))
mid = Rr.rolling(60).mean(); sd = Rr.rolling(60).std(); pb = (Rr - (mid - 2 * sd)) / (4 * sd)
tvp = (P * V[prefs]).rolling(20).mean(); liquid = tvp > 3e8
def dedup(s, gap=20):
    a = s.fillna(False).values.astype(bool).copy()
    for j in range(a.shape[1]):
        last = -999
        for t in range(a.shape[0]):
            if a[t, j]:
                if t - last < gap: a[t, j] = False
                else: last = t
    return pd.DataFrame(a, index=s.index, columns=s.columns)
over = dedup((pb > 1) & (rsiR > 70) & liquid)
print("[우선주 고평가 신호(괴리 BB상단 & RSI>70) 후 우선주−보통주]")
for h in (10, 20, 40, 60):
    F = np.log(P.shift(-h) / P) - np.log(Cm.shift(-h) / Cm)
    for nm, a, b in [("IS", START, IS_END), ("OOS", IS_END, None)]:
        x = F.loc[a:b].where(over.loc[a:b]).stack().dropna()
        print(f"  {h}일 {nm}: 평균 {x.mean():+.2%} 중앙값 {x.median():+.2%} 우선주가 진 비율 {(x<0).mean():.0%} n={len(x)} t={x.mean()/x.std()*np.sqrt(len(x)):.1f}")
# 갈아타기: 그 회사를 계속 보유한다고 할 때, 기본은 우선주, 우선주 고평가면 보통주로, 괴리가 중심선 아래로 오면 다시 우선주로
rp = np.log(P).diff(); rc = np.log(Cm).diff()
state = pd.DataFrame(0, index=P.index, columns=prefs)   # 0=우선주, 1=보통주
sw_in = (pb > 1) & (rsiR > 70); sw_out = pb < 0.5
a = np.zeros(P.shape); cur = np.zeros(P.shape[1])
SI, SO = sw_in.fillna(False).values, sw_out.fillna(False).values
for t in range(len(P)):
    cur = np.where(SI[t], 1, np.where(SO[t], 0, cur)); a[t] = cur
held = pd.DataFrame(a, index=P.index, columns=prefs).shift(1)
switch_ret = (held * rc + (1 - held) * rp)
cost = held.diff().abs() * 2 * (0.00015 + 0.002 + 0.001)      # 갈아탈 때 양쪽 매매비용
ex = (switch_ret - cost - rp).where(liquid.shift(1))           # 항상 우선주 보유 대비 초과
for nm, a_, b_ in [("IS", START, IS_END), ("OOS", IS_END, None)]:
    e = ex.loc[a_:b_]
    yearly = e.sum() / ((e.notna()).sum() / 250)
    yearly = yearly[(e.notna()).sum() > 250]
    print(f"갈아타기 {nm}: 종목별 연평균 초과수익 중앙값 {yearly.median():+.2%}, 평균 {yearly.mean():+.2%}, 플러스 비율 {(yearly>0).mean():.0%} ({len(yearly)}종목), 보통주 보유 비율 {held.loc[a_:b_].where(liquid).stack().mean():.0%}")
pickle.dump((held, rp, rc, liquid), open("switch.pkl", "wb"))
