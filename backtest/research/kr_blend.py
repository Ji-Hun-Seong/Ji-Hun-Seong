import sys, pickle
import numpy as np, pandas as pd
sys.path.insert(0, ".")
from engine import *
piv, idx = load("/tmp/claude-0/btkr/kospi_all.csv.gz", "KPI200")
keep = [c for c in piv["Close"].columns if c.endswith("0")]
piv = {k: v[keep] for k, v in piv.items()}
f = features(piv, idx); C = f["C"]
uni, _ = pickle.load(open("kr_pit.pkl", "rb"))
e = (f["bw_q"].rolling(5).min() < 0.2) & (C > f["up"]) & (f["rsi14"] > 60) & (f["ma50"] > f["ma200"]) & uni
eq, ex, tr = simulate(f, entry=e, score=f["mom"], ascending=False, exit_sig=f["rsi14"] < 40, max_pos=15, hold=250, regime=True)
b = idx.reindex(eq.index); rs, ri = eq.pct_change().fillna(0), b.pct_change().fillna(0)
vs = vi = 0.5; cur = []
for i, d in enumerate(eq.index):
    vs *= 1 + rs.iloc[i]; vi *= 1 + ri.iloc[i]; cur.append(vs + vi)
    if i + 1 < len(eq.index) and eq.index[i + 1].month != d.month: t = vs + vi; vs = vi = t / 2
bl = pd.Series(cur, index=eq.index)
for nm, s in [("전략", eq), ("지수", b), ("50/50", bl)]:
    m = split_metrics(s / s.iloc[0], pd.Series(1.0, index=s.index))
    print(nm, " | ".join(f"{k} {m[k]['CAGR']:+.1%} MDD {m[k]['MDD']:+.1%} Sh {m[k]['Sharpe']:.2f}" for k in m))
