import sys, pickle
import numpy as np, pandas as pd
sys.path.insert(0, ".")
from engine import *
piv, idx = load("/tmp/claude-0/btkr/kospi_all.csv.gz", "KPI200")
keep = [c for c in piv["Close"].columns if c.endswith("0")]
piv = {k: v[keep] for k, v in piv.items()}
f = features(piv, idx); C = f["C"]
uni, mom_r = pickle.load(open("kr_pit.pkl", "rb"))
def show(name, m, extra=""):
    print(f"{name:34s} | " + " | ".join(f"{k} {m[k]['CAGR']:+.1%} MDD {m[k]['MDD']:+.1%} Sh {m[k]['Sharpe']:.2f}" for k in m) + extra, flush=True)
bench = idx.loc[START:]
show("코스피200 보유", split_metrics(bench, pd.Series(1.0, index=bench.index)))

# ---------- H2 시장 폭: 유니버스 중 BB하단 이탈 & RSI<30 비율 ----------
u = uni & C.notna()
br = ((C < f["lo"]) & (f["rsi14"] < 30) & u).sum(axis=1) / u.sum(axis=1)
br_hi = ((C > f["up"]) & (f["rsi14"] > 70) & u).sum(axis=1) / u.sum(axis=1)
r = idx.pct_change()
fwd20 = idx.shift(-20) / idx - 1
print("\n[H2] 공포 폭(하단이탈&RSI<30 비율)별 코스피200 20일 후 수익률")
for lo, hi in [(0, .02), (.02, .05), (.05, .10), (.10, .20), (.20, 1.01)]:
    m = (br >= lo) & (br < hi)
    for nm, a, b in [("IS", START, IS_END), ("OOS", IS_END, None)]:
        x = fwd20.loc[a:b][m.loc[a:b]].dropna()
        print(f"  폭 {lo:.0%}~{hi:.0%} {nm}: {x.mean():+.2%} (일수 {len(x)}, 상승확률 {(x>0).mean():.0%})")
def idx_strat(wfun):
    w = wfun().shift(1).fillna(0)
    ret = w * r + (1 - w) * 0.02 / 252 - w.diff().abs().fillna(0) * 0.0005
    return (1 + ret.loc[START:].fillna(0)).cumprod(), w.loc[START:]
ma200 = idx.rolling(200).mean()
def trend(): return (idx > ma200).astype(float)
def trend_panic(th=0.10, hold=20):
    w = (idx > ma200).astype(float).values.copy(); cnt = 0
    for t in range(len(w)):
        if br.iloc[t] >= th: cnt = hold
        if cnt > 0: w[t] = 1.0; cnt -= 1
    return pd.Series(w, index=idx.index)
for nm, fn in [("200일선 추세", trend), ("추세+공포폭10% 매수(20일)", lambda: trend_panic(.10, 20)), ("추세+공포폭5% 매수(20일)", lambda: trend_panic(.05, 20)), ("추세+공포폭10% 매수(40일)", lambda: trend_panic(.10, 40))]:
    eq, w = idx_strat(fn); show(nm, split_metrics(eq, w), f" | 평균비중 {w.mean():.2f}")

# ---------- H3 상대강도 스퀴즈: RS = 종목/코스피200 ----------
RS = C.div(idx, axis=0)
m20 = RS.rolling(20).mean(); s20 = RS.rolling(20).std()
rs_up = m20 + 2 * s20
rs_bwq = (4 * s20 / m20).rolling(250, min_periods=120).rank(pct=True)
rs_rsi = RS.apply(lambda s: rsi(s, 14))
for q, ri, ro in [(0.2, 60, 40), (0.2, 55, 45), (0.3, 60, 40)]:
    e = (rs_bwq.rolling(5).min() < q) & (RS > rs_up) & (rs_rsi > ri) & (C > f["ma200"]) & uni
    eq, ex, tr = simulate(f, entry=e, score=f["mom"], ascending=False, exit_sig=rs_rsi < ro, max_pos=15, hold=250, regime=True)
    m = split_metrics(eq, ex, tr); show(f"[H3] RS스퀴즈 q{q} in{ri} out{ro}", m, f" | N{m['ALL']['N']} 건당 {m['ALL']['AvgTr']:+.1%} 노출 {m['ALL']['Expo']:.0%}")
# 비교: 가격 스퀴즈(이전 최종)
e = (f["bw_q"].rolling(5).min() < 0.2) & (C > f["up"]) & (f["rsi14"] > 60) & (f["ma50"] > f["ma200"]) & uni
eq, ex, tr = simulate(f, entry=e, score=f["mom"], ascending=False, exit_sig=f["rsi14"] < 40, max_pos=15, hold=250, regime=True)
show("(비교) 가격 스퀴즈", split_metrics(eq, ex, tr))

# ---------- H4 거래대금 BB: 가격은 조용, 거래대금만 상단 돌파 ----------
TV = np.log((C * piv["Volume"]).replace(0, np.nan))
tv_up = TV.rolling(60).mean() + 2 * TV.rolling(60).std()
for pblo, pbhi in [(0.4, 0.8), (0.5, 1.0)]:
    e = (TV > tv_up) & (f["pb"] > pblo) & (f["pb"] < pbhi) & (f["rsi14"] > 45) & (f["rsi14"] < 65) & (C > f["ma200"]) & uni
    eq, ex, tr = simulate(f, entry=e, score=f["mom"], ascending=False, exit_sig=(f["rsi14"] < 40) | (f["rsi14"] > 75), max_pos=15, hold=40, regime=True)
    m = split_metrics(eq, ex, tr); show(f"[H4] 거래대금BB %b{pblo}-{pbhi}", m, f" | N{m['ALL']['N']} 건당 {m['ALL']['AvgTr']:+.1%}")
pickle.dump(br, open("breadth.pkl", "wb"))
