import sys, pickle
import numpy as np, pandas as pd
sys.path.insert(0, ".")
import engine
from engine import *
piv, idx = load("/tmp/claude-0/btkr/kospi_all.csv.gz", "KPI200")
keep = [c for c in piv["Close"].columns if c.endswith("0")]
piv = {k: v[keep] for k, v in piv.items()}
f = features(piv, idx); C = f["C"]
R = pd.read_pickle("dart_events2.pkl")
dates = C.index
liq = f["tv"] >= 3e8
def ev_matrix(types, extra=None):
    M = np.zeros(C.shape, bool); cols = {c: i for i, c in enumerate(C.columns)}
    g = R[R.type.isin(types)]
    for d, c in zip(g.date, g.code):
        t = dates.searchsorted(d, side="right") - 1
        if 0 <= t < len(dates) and c in cols: M[t, cols[c]] = True
    M = pd.DataFrame(M, index=dates, columns=C.columns) & liq
    return M & extra if extra is not None else M
def show(name, eq, ex, tr):
    m = split_metrics(eq, ex, tr)
    print(f"{name:42s} | " + " | ".join(f"{k} {m[k]['CAGR']:+.1%} MDD {m[k]['MDD']:+.1%} Sh {m[k]['Sharpe']:.2f}" for k in m) +
          f" | N{m['ALL'].get('N',0)} 승률 {m['ALL'].get('Win',0):.0%} 건당 {m['ALL'].get('AvgTr',0):+.2%} 노출 {m['ALL']['Expo']:.0%}", flush=True)
    return m
bench = idx.loc[START:]
show("코스피200", bench, pd.Series(1.0, index=bench.index), None)
up = C > f["ma200"]; weak = (f["rsi14"] < 50)
never = C.isna()  # 청산 신호 없음(기간 만료로만)
S = {
 "A 자사주(취득·신탁) 20일":            dict(entry=ev_matrix(["자사주취득", "자사주신탁"]), exit_sig=never, hold=20),
 "A' 자사주 + RSI<50 20일":            dict(entry=ev_matrix(["자사주취득", "자사주신탁"], weak), exit_sig=never, hold=20),
 "A'' 자사주 + RSI<50, RSI>70 익절":     dict(entry=ev_matrix(["자사주취득", "자사주신탁"], weak), exit_sig=f["rsi14"] > 70, hold=20),
 "A3 자사주 + RSI<50 40일":            dict(entry=ev_matrix(["자사주취득", "자사주신탁"], weak), exit_sig=never, hold=40),
 "B 공급계약 + 200일선 위 60일":          dict(entry=ev_matrix(["공급계약"], up), exit_sig=never, hold=60),
 "B' 공급계약 + 200일선 위, 이탈 시 청산":   dict(entry=ev_matrix(["공급계약"], up), exit_sig=C < f["ma200"], hold=60),
 "C 배당증가20% (30억 미만) 60일":        dict(entry=ev_matrix(["배당증가(20%↑)"], f["tv"] < 3e9), exit_sig=never, hold=60),
 "D 무상증자 20일":                     dict(entry=ev_matrix(["무상증자"]), exit_sig=never, hold=20),
 "E 호재 묶음(A'+C+D) 30일":             dict(entry=ev_matrix(["자사주취득", "자사주신탁"], weak) | ev_matrix(["배당증가(20%↑)"], f["tv"] < 3e9) | ev_matrix(["무상증자"]), exit_sig=never, hold=30),
}
res = {}
for name, kw in S.items():
    for mp in (10,):
        eq, ex, tr = simulate(f, score=f["tv"], ascending=True, max_pos=mp, regime=False, **kw)
        res[name] = (eq, show(name, eq, ex, tr))
pickle.dump({k: v[0] for k, v in res.items()}, open("dart_eqs.pkl", "wb"))
# 플라시보: A'와 같은 빈도의 무작위 진입(유동성 조건 동일, RSI<50 동일)
base = S["A' 자사주 + RSI<50 20일"]["entry"]; freq = base.loc[START:].values.mean(); out = []
for seed in range(20):
    rnd = pd.DataFrame(np.random.default_rng(seed).random(C.shape) < freq, index=dates, columns=C.columns) & liq & weak
    eq, ex, tr = simulate(f, entry=rnd, score=f["tv"], ascending=True, max_pos=10, exit_sig=never, hold=20)
    out.append(metrics(eq)["CAGR"])
print(f"플라시보(A' 동일조건 무작위 진입 20회): CAGR 평균 {np.mean(out):+.1%}, 최대 {np.max(out):+.1%}")
