import numpy as np, pandas as pd
exec(open('sell.py').read().split("G=R[R.good]")[0])
X = pd.read_pickle('X.pkl')
def s(x):
    x = x.dropna(); n = len(x); return f"{x.mean():+.2%}(t{x.mean()/x.std()*np.sqrt(n):.1f},n{n})"
small = X['size'] < .01; hipbr = X.pbr >= 1
F = {'기존 좋음': X.good, '좋음 & 규모<1% 제외': X.good & ~small, '좋음 & PBR≥1 제외': X.good & ~hipbr,
     '좋음 & 둘 다 제외': X.good & ~small & ~hipbr, '전체 & 둘 다 제외': ~small & ~hipbr}
for k, m in F.items():
    g = X[m]; print(f"{k:18s} 10일 IS {s(g[g.dt<='2020-12-31'].x10)} OOS {s(g[g.dt>'2020-12-31'].x10)}")
    for sl in [5, 7]:
        x = run(g, slots=sl); print(f"   {sl}종목 연 {x['연']:.1%} IS {x['IS']:.1%} OOS {x['OOS']:.1%} MDD {x['MDD']:.0%} Sharpe {x['Sharpe']:.2f} 최악연 {x['최악연']:+.1%}")
