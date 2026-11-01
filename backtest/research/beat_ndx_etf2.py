"""6차-3: 실제 운용형 — TQQQ(합성 3배)+현금 비중으로 목표 레버리지 구현, 주 1회 리밸런싱(변화 5%p 이상일 때만)
목표 레버리지 = min(cap, 목표변동성 / 최근 W일 변동성), 나스닥100 < N일선이면 0
"""
import sys, itertools
import numpy as np, pandas as pd
exec(open("beat_ndx_etf.py").read().split('print(f"\\n{\'\':40s}')[0])
tq = lev(3)
week_end = pd.Series(days, index=days).dt.to_period("W").ne(pd.Series(days, index=days).dt.to_period("W").shift(-1))

def run_w(target_L, band=0.05):
    tgt_w = (target_L / 3).clip(0, 1)
    w, cur, out = np.zeros(len(days)), 0.0, np.zeros(len(days))
    tq_v, rf_v, we, tw = tq.values, rf.values, week_end.values, tgt_w.values
    for i in range(len(days)):
        # 오늘 수익 (어제 정한 비중)
        out[i] = cur * tq_v[i] + (1 - cur) * rf_v[i]
        cur = cur * (1 + tq_v[i]) / (1 + out[i]) if (1 + out[i]) > 0 else 0     # 비중 드리프트
        if we[i] and not np.isnan(tw[i]) and abs(tw[i] - cur) > band:
            out[i] -= abs(tw[i] - cur) * COST
            cur = tw[i]
        w[i] = cur
    return pd.Series(out, index=days), pd.Series(w, index=days)

print(f"\n{'':40s} | " + " | ".join(f"{k}" for k in PER))
B = show("나스닥100 보유", r)
res = []
for tv, n, W, cap in itertools.product((0.3, 0.35, 0.4, 0.45, 0.5, 0.6), (0, 150, 200, 250), (20, 60), (2, 3)):
    v = r.rolling(W).std() * np.sqrt(252)
    L = (tv / v).clip(upper=cap)
    if n:
        L = L * (ndx > ndx.rolling(n).mean())
    x, w = run_w(L)
    out = {k: perf(x, a, b) for k, (a, b) in PER.items()}
    res.append(dict(tv=tv, n=n, W=W, cap=cap, avgL=float((w * 3).loc["2015-11-01":].mean()), **{k: v[0] for k, v in out.items()},
                    **{k + "_mdd": v[1] for k, v in out.items()}))
g = pd.DataFrame(res)
keys = ["10년(2015-11~)", "IS 2015-11~2020", "OOS 2021~", "장기 1990~"]
g["pass"] = np.all([g[k] > B[k] for k in keys], axis=0)
print(f"{len(g)}개 중 10년·IS·OOS·장기 모두 나스닥100 초과: {g['pass'].mean():.0%}")
for col in ["tv", "n", "W", "cap"]:
    print(col, g.groupby(col)["pass"].mean().round(2).to_dict(), "| 장기 MDD 중앙값", g.groupby(col)["장기 1990~_mdd"].median().round(2).to_dict())
cols = ["tv", "n", "W", "cap", "avgL"] + keys + ["닷컴 2000~2002", "금융위기 2007~2009", "10년(2015-11~)_mdd", "장기 1990~_mdd"]
print(g[g["pass"]].sort_values("장기 1990~_mdd", ascending=False)[cols].head(15).round(3).to_string())
g.to_csv("beat_ndx_etf2_grid.csv", index=False)
