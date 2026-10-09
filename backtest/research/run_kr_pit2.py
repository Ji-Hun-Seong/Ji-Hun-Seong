import sys, pickle, itertools
import numpy as np, pandas as pd
sys.path.insert(0, ".")
from engine import *
piv, idx = load("/tmp/claude-0/btkr/kospi_all.csv.gz", "KPI200")
keep = [c for c in piv["Close"].columns if c.endswith("0")]
piv = {k: v[keep] for k, v in piv.items()}
f = features(piv, idx); C = f["C"]
uni, mom_r = pickle.load(open("kr_pit.pkl", "rb"))
def s3(q=0.2, w=5, ri=60, ro=40, mp=15):
    e = (f["bw_q"].rolling(w).min() < q) & (C > f["up"]) & (f["rsi14"] > ri) & (f["ma50"] > f["ma200"]) & uni
    return dict(entry=e, score=f["mom"], ascending=False, exit_sig=f["rsi14"] < ro, max_pos=mp, hold=250, regime=True)
base = s3(); freq = base["entry"].loc[START:].values.mean()
res = []
for seed in range(20):
    rnd = pd.DataFrame(np.random.default_rng(seed).random(C.shape) < freq, index=C.index, columns=C.columns) & uni & C.notna()
    k = s3(); k["entry"] = rnd; k["score"] = f["mom"] * 0
    eq, ex, tr = simulate(f, **k); m = metrics(eq); res.append((m["CAGR"], m["Sharpe"]))
r = np.array(res); print(f"플라시보(무작위 진입 20회): CAGR 평균 {r[:,0].mean():+.1%} 최대 {r[:,0].max():+.1%}, Sharpe 평균 {r[:,1].mean():.2f} 최대 {r[:,1].max():.2f}")
rows = []
for q, w, ri, ro, mp in itertools.product([0.1, 0.2, 0.3], [5, 10], [55, 60, 70], [35, 40, 45], [10, 15, 20]):
    eq, ex, tr = simulate(f, **s3(q, w, ri, ro, mp)); m = split_metrics(eq, ex)
    rows.append((q, w, ri, ro, mp, m["ALL"]["CAGR"], m["ALL"]["Sharpe"], m["ALL"]["MDD"], m["IS"]["CAGR"], m["IS"]["Sharpe"], m["OOS"]["CAGR"], m["OOS"]["Sharpe"]))
g = pd.DataFrame(rows, columns="q w ri ro mp CAGR Sh MDD IS_CAGR IS_Sh OOS_CAGR OOS_Sh".split())
print(f"그리드 {len(g)}개: 전체 CAGR 중앙값 {g.CAGR.median():+.1%} (하위10% {g.CAGR.quantile(.1):+.1%}), 지수(13.9%) 초과 비율 {(g.CAGR>0.139).mean():.0%}, Sharpe 중앙값 {g.Sh.median():.2f}")
print(f"IS 중앙값 {g.IS_CAGR.median():+.1%}/Sh {g.IS_Sh.median():.2f} (지수 8.9%/0.59), OOS 중앙값 {g.OOS_CAGR.median():+.1%}/Sh {g.OOS_Sh.median():.2f} (지수 18.1%/0.72)")
g = g.sort_values("IS_Sh", ascending=False)
print("IS 기준 상위 1/3의 OOS: CAGR 중앙값 %+.1f%%, Sharpe 중앙값 %.2f" % (g.head(len(g)//3).OOS_CAGR.median()*100, g.head(len(g)//3).OOS_Sh.median()))
b = g.iloc[0]; print("IS 1등 파라미터", b[["q","w","ri","ro","mp"]].to_dict(), f"→ OOS {b.OOS_CAGR:+.1%} Sh {b.OOS_Sh:.2f}")
cur = g[(g.q==0.2)&(g.w==5)&(g.ri==60)&(g.ro==40)&(g.mp==15)].iloc[0]
print("현재 규칙(0.2/5/60/40/15)", f"전체 {cur.CAGR:+.1%} Sh {cur.Sh:.2f} MDD {cur.MDD:+.1%} | IS {cur.IS_CAGR:+.1%} | OOS {cur.OOS_CAGR:+.1%}")
eq, ex, tr = simulate(f, **s3())
yr = pd.DataFrame({"전략": eq.resample("YE").last().pct_change(), "지수": idx.loc[START:].resample("YE").last().pct_change()})
yr.index = yr.index.year; print(yr.iloc[1:].map(lambda x: f"{x:+.0%}").T.to_string())
g.to_csv("kr_pit_grid.csv", index=False)
