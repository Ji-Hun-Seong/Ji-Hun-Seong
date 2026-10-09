import sys, itertools
import numpy as np, pandas as pd
sys.path.insert(0, ".")
import engine
from engine import *
piv, idx = load("/tmp/claude-0/btkr/kospi_all.csv.gz", "KPI200")
names = pd.read_csv("/tmp/claude-0/btkr/kospi_all_members.csv", dtype=str).set_index("code")["name"]
C, O, V = piv["Close"], piv["Open"], piv["Volume"]
prefs = [c for c in C.columns if not c.endswith("0") and (c[:5] + "0") in C.columns]
P = C[prefs]; Cm = C[[p[:5] + "0" for p in prefs]].set_axis(prefs, axis=1)
Rr = np.log(P / Cm)
rsiR = Rr.apply(lambda s: rsi(np.exp(s), 14))
tvp = (P * V[prefs]).rolling(20).mean()
f = {"C": P, "O": O[prefs], "regime": idx > idx.rolling(200).mean(), "idx": idx}
def bands(N):
    mid = Rr.rolling(N).mean(); sd = Rr.rolling(N).std()
    return (Rr - (mid - 2 * sd)) / (4 * sd)
PB = {N: bands(N) for N in (40, 60, 120)}
def strat(N=60, pb_in=0.0, r_in=30, pb_out=0.5, liq=3e8, mp=8, hold=40):
    pb = PB[N]
    return dict(entry=(pb < pb_in) & (rsiR < r_in) & (tvp > liq), score=rsiR, exit_sig=pb > pb_out, max_pos=mp, hold=hold, regime=True)
# 이벤트 스터디(수정): 신호 후 우선주-보통주 초과수익
pb = PB[60]; liquid = tvp > 3e8
sig = (pb < 0) & (rsiR < 30) & liquid
print("[이벤트] 신호 후 우선주−보통주 초과수익 (같은 종목 중복 신호는 20일 간격으로 제거)")
s2 = sig.copy()
arr = s2.fillna(False).values.astype(bool).copy()
for j in range(arr.shape[1]):
    last = -999
    for t in range(arr.shape[0]):
        if arr[t, j]:
            if t - last < 20: arr[t, j] = False
            else: last = t
s2 = pd.DataFrame(arr, index=sig.index, columns=sig.columns)
for h in (10, 20, 40):
    F = np.log(P.shift(-h) / P) - np.log(Cm.shift(-h) / Cm)
    for nm, a, b in [("IS", START, IS_END), ("OOS", IS_END, None)]:
        x = F.loc[a:b].where(s2.loc[a:b]).stack().dropna()
        base = F.loc[a:b].where(liquid.loc[a:b]).stack().dropna()
        print(f"  {h}일 {nm}: {x.mean():+.2%} 중앙값 {x.median():+.2%} 승률 {(x>0).mean():.0%} n={len(x)} (평소 {base.mean():+.2%}, t={x.mean()/x.std()*np.sqrt(len(x)):.1f})")
base = strat()
eq, ex, tr = simulate(f, **base)
m = split_metrics(eq, ex, tr)
print("\n기준:", " | ".join(f"{k} {m[k]['CAGR']:+.1%} MDD {m[k]['MDD']:+.1%} Sh {m[k]['Sharpe']:.2f}" for k in m))
yr = eq.resample("YE").last().pct_change(); yr.iloc[0] = eq.resample("YE").last().iloc[0] / eq.iloc[0] - 1
yi = idx.loc[START:].resample("YE").last().pct_change(); yi.iloc[0] = idx.loc[START:].resample("YE").last().iloc[0] / idx.loc[START:].iloc[0] - 1
print("연도별 전략:", " ".join(f"{d.year}:{v:+.0%}" for d, v in yr.items()))
print("연도별 지수:", " ".join(f"{d.year}:{v:+.0%}" for d, v in yi.items()))
# 거래 기여 집중도
import engine as E
# 거래 단위 상세를 위해 간단 재계산: 진입일/종목은 엔진이 저장하지 않으므로 수익 분포만
rets = tr.ret.sort_values(ascending=False)
print(f"거래 {len(rets)}회, 상위 10건 합 {rets.head(10).sum():+.1%} / 전체 합 {rets.sum():+.1%}, 상위10 제외 평균 {rets.iloc[10:].mean():+.2%}, 중앙값 {rets.median():+.2%}")
print("\n[민감도] 한 번에 하나씩")
for k, vals in {"N": [40, 120], "pb_in": [-0.2, 0.1], "r_in": [25, 35, 40], "pb_out": [0.3, 0.8], "liq": [1e8, 1e9], "mp": [5, 12], "hold": [20, 60]}.items():
    for v in vals:
        eq, ex, tr = simulate(f, **strat(**{k: v})); m = split_metrics(eq, ex, tr)
        print(f"  {k}={v}: " + " | ".join(f"{kk} {m[kk]['CAGR']:+.1%} Sh {m[kk]['Sharpe']:.2f}" for kk in m) + f" | N{m['ALL'].get('N',0)}")
print("\n[비용] 슬리피지")
for sl in (0.003, 0.005):
    engine.BUY_COST = 0.00015 + sl; engine.SELL_COST = 0.00015 + 0.002 + sl
    eq, ex, tr = simulate(f, **base); m = split_metrics(eq, ex, tr)
    print(f"  편도 {sl:.1%}: " + " | ".join(f"{k} {m[k]['CAGR']:+.1%} Sh {m[k]['Sharpe']:.2f}" for k in m))
engine.BUY_COST = 0.00015 + 0.002; engine.SELL_COST = 0.00015 + 0.002 + 0.002
# 그리드 + 워크포워드
rows = []
for N, pin, rin, pout, mp in itertools.product([40, 60, 120], [-0.1, 0.0, 0.1], [25, 30, 35], [0.3, 0.5, 0.8], [5, 8, 12]):
    eq, ex, tr = simulate(f, **strat(N, pin, rin, pout, 3e8, mp)); m = split_metrics(eq, ex)
    rows.append((N, pin, rin, pout, mp, m["ALL"]["CAGR"], m["ALL"]["Sharpe"], m["IS"]["CAGR"], m["IS"]["Sharpe"], m["OOS"]["CAGR"], m["OOS"]["Sharpe"]))
g = pd.DataFrame(rows, columns="N pin rin pout mp CAGR Sh IS IS_Sh OOS OOS_Sh".split())
print(f"\n[그리드 {len(g)}개] 전체 CAGR 중앙값 {g.CAGR.median():+.1%} 하위10% {g.CAGR.quantile(.1):+.1%}, 지수(13.9%) 초과 {(g.CAGR>.139).mean():.0%}, Sharpe 중앙값 {g.Sh.median():.2f}")
print(f"  IS 중앙값 {g.IS.median():+.1%}/{g.IS_Sh.median():.2f}, OOS 중앙값 {g.OOS.median():+.1%}/{g.OOS_Sh.median():.2f}")
g = g.sort_values("IS_Sh", ascending=False); b = g.iloc[0]
print(f"  IS 1등 {b[['N','pin','rin','pout','mp']].to_dict()} → OOS {b.OOS:+.1%} Sh {b.OOS_Sh:.2f}; IS 상위1/3의 OOS 중앙값 {g.head(len(g)//3).OOS.median():+.1%}/{g.head(len(g)//3).OOS_Sh.median():.2f}")
g.to_csv("h1_grid.csv", index=False)
eq.to_csv("h1_eq.csv")
