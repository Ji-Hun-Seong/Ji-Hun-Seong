import sys
import numpy as np, pandas as pd
sys.path.insert(0, ".")
from engine import *
piv, idx = load("/tmp/claude-0/btkr/kospi_all.csv.gz", "KPI200")
keep = [c for c in piv["Close"].columns if c.endswith("0")]
piv = {k: v[keep] for k, v in piv.items()}
f = features(piv, idx)
R = pd.read_pickle("dart_events2.pkl")
cols = {c: i for i, c in enumerate(f["C"].columns)}
ti = R.t.values - 1; ci = R.code.map(cols).values
R["tv"] = f["tv"].values[ti, ci]
def s(x):
    x = x.dropna(); return f"{x.mean():+.2%}(n{len(x)},승{(x>0).mean():.0%},t{x.mean()/x.std()*np.sqrt(len(x)) if len(x)>2 else 0:.1f})"
print("거래대금 구간별(20일 평균)")
for typ in ["자사주신탁", "자사주취득", "공급계약", "무상증자", "배당증가(20%↑)", "자사주소각"]:
    g = R[R.type == typ]
    print(f"\n[{typ}] n={len(g)}")
    for nm, m in [("<5억", g.tv < 5e8), ("5~30억", (g.tv >= 5e8) & (g.tv < 3e9)), ("30~150억", (g.tv >= 3e9) & (g.tv < 1.5e10)), (">150억", g.tv >= 1.5e10)]:
        a, b = g[m & (g.date <= IS_END)], g[m & (g.date > IS_END)]
        print(f"  {nm:8s} 20일 IS {s(a.x20)} OOS {s(b.x20)} | 60일 IS {s(a.x60)} OOS {s(b.x60)}")
    g2 = g[g.tv >= 5e8]
    for nm, m in [("RSI<50", g2.rsi14 < 50), ("RSI>=50", g2.rsi14 >= 50), ("%b<0.5", g2.pb < 0.5), ("%b>=0.5", g2.pb >= 0.5), ("200일선 위", g2.up), ("아래", ~g2.up)]:
        a, b = g2[m & (g2.date <= IS_END)], g2[m & (g2.date > IS_END)]
        print(f"   (5억↑) {nm:8s} 20일 IS {s(a.x20)} OOS {s(b.x20)} | 60일 IS {s(a.x60)} OOS {s(b.x60)}")
