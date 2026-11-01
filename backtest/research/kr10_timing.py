"""7차-4: 자사주 공시 진입 시점 — 공시일 종가(애프터마켓 근사) vs 다음 날 시가"""
import sys, pickle
import numpy as np, pandas as pd
sys.path.insert(0, ".")
from engine import *
piv, idx = load("/tmp/claude-0/btkr/kospi_all.csv.gz", "KPI200")
keep = [c for c in piv["Close"].columns if c.endswith("0")]
piv = {k: v[keep] for k, v in piv.items()}
C, O = piv["Close"], piv["Open"]
tv = (C * piv["Volume"]).rolling(20).mean()
R = pd.read_pickle("dart_events.pkl")
R = R[R.type.isin(["자사주취득", "자사주신탁"])]
dates = C.index; cols = {c: i for i, c in enumerate(C.columns)}
Cv, Ov, TV, I = C.values, O.values, tv.values, idx.reindex(dates).values
rows = []
for d, c, typ in zip(R.date, R.code, R.type):
    if c not in cols: continue
    t = dates.searchsorted(d, side="right") - 1          # 공시일(또는 직전 거래일)
    j = cols[c]
    if t < 1 or t + 11 >= len(dates) or np.isnan(Cv[t, j]) or np.isnan(Ov[t + 1, j]) or TV[t, j] < 3e8: continue
    rows.append(dict(date=dates[t], code=c, type=typ, tv=TV[t, j],
        day=Cv[t, j] / Cv[t - 1, j] - 1,                       # 공시 당일 (장중 공시 반응 포함)
        gap=Ov[t + 1, j] / Cv[t, j] - 1,                        # 공시일 종가 → 다음 날 시가
        from_close=Cv[t + 10, j] / Cv[t, j] - 1,                # 공시일 종가 진입 → 10일 뒤
        from_open=Cv[t + 10, j] / Ov[t + 1, j] - 1,             # 다음 날 시가 진입 → 10일 뒤
        mkt_c=I[t + 10] / I[t] - 1, mkt_o=I[t + 10] / I[t] - 1))
X = pd.DataFrame(rows)
X = X[(X.date >= START)]
def s(x):
    x = x.dropna(); return f"{x.mean():+.2%} (중앙 {x.median():+.2%}, 승률 {(x > 0).mean():.0%}, t={x.mean() / x.std() * np.sqrt(len(x)):.1f})"
print(f"자사주 공시 {len(X)}건 (거래대금 3억↑, 2015-11~)")
for nm, g in [("전체", X), ("2015~2020", X[X.date <= IS_END]), ("2021~", X[X.date > IS_END]),
              ("거래대금 30억 미만(대체로 NXT 미지원 소형주)", X[X.tv < 3e9]), ("거래대금 30억 이상", X[X.tv >= 3e9])]:
    print(f"\n[{nm}] n={len(g)}")
    print("  공시 당일 등락      ", s(g.day))
    print("  종가→다음날 시가 갭  ", s(g.gap))
    print("  종가 진입 10일 보유  ", s(g.from_close))
    print("  시가 진입 10일 보유  ", s(g.from_open))
    print("  차이(종가-시가 진입) ", s(g.from_close - g.from_open))
# 갭 크기별: 다음 날 시가가 이미 많이 오른 경우
print("\n[다음 날 시가 갭 크기별 → 시가 진입 후 10일]")
for lo, hi in [(-1, 0), (0, 0.02), (0.02, 0.05), (0.05, 1)]:
    g = X[(X.gap > lo) & (X.gap <= hi)]
    print(f"  갭 {lo:+.0%}~{hi:+.0%}: n={len(g)}, 시가 진입 10일 {s(g.from_open)}")
