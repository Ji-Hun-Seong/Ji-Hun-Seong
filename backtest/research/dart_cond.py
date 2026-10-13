import sys, pickle
import numpy as np, pandas as pd
sys.path.insert(0, ".")
from engine import *
piv, idx = load("/tmp/claude-0/btkr/kospi_all.csv.gz", "KPI200")
keep = [c for c in piv["Close"].columns if c.endswith("0")]
piv = {k: v[keep] for k, v in piv.items()}
f = features(piv, idx)
R = pd.read_pickle("dart_events.pkl")
dates = f["C"].index; cols = {c: i for i, c in enumerate(f["C"].columns)}
ti = R.t.values - 1; ci = R.code.map(cols).values
for k in ("rsi14", "pb", "ma200", "C"):
    R[k] = f[k].values[ti, ci]
R["up"] = R.C > R.ma200
R["regime"] = f["regime"].values[ti].astype(bool)
def s(x):
    x = x.dropna(); return f"{x.mean():+.2%}(n{len(x)},t{x.mean()/x.std()*np.sqrt(len(x)) if len(x)>2 else 0:.1f})"
for typ in ["자사주신탁", "자사주취득", "공급계약", "무상증자", "액면분할"]:
    g = R[(R.type == typ) & R.in_uni]
    print(f"\n[{typ}] 유니버스 내 n={len(g)}")
    for nm, m in [("RSI<40", g.rsi14 < 40), ("RSI40~60", g.rsi14.between(40, 60)), ("RSI>60", g.rsi14 > 60),
                  ("%b<0.3", g.pb < 0.3), ("%b>0.7", g.pb > 0.7), ("200일선 위", g.up), ("200일선 아래", ~g.up), ("시장필터 on", g.regime)]:
        a, b = g[m & (g.date <= IS_END)], g[m & (g.date > IS_END)]
        print(f"  {nm:10s} 20일 IS {s(a.x20)} OOS {s(b.x20)} | 60일 IS {s(a.x60)} OOS {s(b.x60)}")
R.to_pickle("dart_events2.pkl")
