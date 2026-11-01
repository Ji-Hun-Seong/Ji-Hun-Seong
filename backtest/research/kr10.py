"""7차: 한국 주식 연 10% 안팎을 2015~2020·2021~2026 모두 꾸준히 — 후보 비교·조합"""
import sys, pickle, itertools
import numpy as np, pandas as pd
exec(open("dart_strat.py").read().split("S = {")[0])
uni, _ = pickle.load(open("kr_pit.pkl", "rb"))
E = pd.read_csv("/tmp/bt/etf_prices.csv.gz", parse_dates=["Date"]).pivot(index="Date", columns="code", values="Close").sort_index()
RF = 0.02 / 252                                # 원화 단기금리 근사(연 2%)

def m(eq, a=None, b=None):
    e = eq[(eq.index >= (a or START)) & ((eq.index <= b) if b else True)].dropna()
    yrs = (e.index[-1] - e.index[0]).days / 365.25; rr = e.pct_change().dropna()
    return (e.iloc[-1] / e.iloc[0]) ** (1 / yrs) - 1, (e / e.cummax() - 1).min(), rr.mean() / rr.std() * np.sqrt(250)
def row(name, eq):
    a, i, o = m(eq), m(eq, None, IS_END), m(eq, IS_END + pd.Timedelta(days=1))
    y = eq[eq.index >= START].resample("YE").last().pct_change().dropna()
    y0 = eq[eq.index >= START].resample("YE").last()
    print(f"{name:40s} | {a[0]:+.1%} MDD{a[1]:+.0%} Sh{a[2]:.2f} | IS {i[0]:+.1%} MDD{i[1]:+.0%} | OOS {o[0]:+.1%} MDD{o[1]:+.0%} | 플러스 연도 {(y > 0).mean():.0%}, 최악 {y.min():+.0%}", flush=True)
    return a, i, o

print(f"{'':40s} | 전체(2015-11~) | IS 2015-11~2020 | OOS 2021~ | 연도별")
K = idx / idx.loc[START:].iloc[0]
row("코스피200 보유", K)

# ① 지수 타이밍: 코스피200 목표변동성 + 200일선, 레버리지 ETF(2배) 사용
r = idx.pct_change().fillna(0)
def timing(tv, n=200, cap=2.0, W=20):
    v = r.rolling(W).std() * np.sqrt(250)
    L = (tv / v).clip(upper=cap) * (idx > idx.rolling(n).mean())
    pos = L.shift(1).fillna(0)
    ret = pos * r - (pos - 1).clip(lower=0) * RF - (pos > 1) * 0.0064 / 250 + (1 - pos).clip(lower=0) * RF
    ret -= pos.diff().abs().fillna(0) * 0.0005
    return (1 + ret).cumprod()
print("\n[① 코스피200 목표변동성 레버리지 + 추세]")
T = {}
for tv, n in itertools.product((0.1, 0.15, 0.2, 0.25), (100, 200)):
    T[(tv, n)] = timing(tv, n); row(f"목표변동성 {tv:.0%}, {n}일선", T[(tv, n)])

# ② 개별 종목 전략
print("\n[② 종목 전략]")
ev = ev_matrix(["자사주취득", "자사주신탁"])
rnd = pd.DataFrame(np.random.default_rng(1).random(C.shape), index=dates, columns=C.columns)
eqB, exB, trB = simulate(f, entry=ev, score=rnd, max_pos=10, exit_sig=f["rsi14"] > 70, hold=10); row("B 자사주 공시 스윙 (10일, RSI>70 익절)", eqB)
sq = (f["bw_q"].rolling(5).min() < 0.2) & (C > f["up"]) & (f["rsi14"] > 60) & (f["ma50"] > f["ma200"]) & uni
eqA, exA, trA = simulate(f, entry=sq, score=f["mom"], ascending=False, exit_sig=f["rsi14"] < 40, max_pos=15, hold=250, regime=True); row("A 스퀴즈 돌파", eqA)
eqBp, _, _ = simulate(f, entry=ev, score=rnd, max_pos=10, exit_sig=f["rsi14"] > 70, hold=10, park="smart"); row("B + 쉬는 돈 코스피200(200일선 위일 때)", eqBp)

# ③ 조합 (월 리밸런싱)
print("\n[③ 조합 — 월 1회 비중 재조정]")
def blend(curves, ws):
    df = pd.DataFrame(curves).loc[START:].ffill().pct_change().fillna(0)
    v = np.array(ws, float); out = []
    for i, d in enumerate(df.index):
        v = v * (1 + df.iloc[i].values); out.append(v.sum())
        if i + 1 < len(df.index) and df.index[i + 1].month != d.month:
            v = v.sum() * np.array(ws, float)
    return pd.Series(out, index=df.index)
res = []
for (tv, n), (wa, wb, wt) in itertools.product([(0.15, 200), (0.2, 200), (0.2, 100)], [(0, .5, .5), (.5, .5, 0), (1/3, 1/3, 1/3), (.25, .5, .25), (0, 1/3, 2/3), (.25, .25, .5)]):
    e = blend({"A": eqA, "B": eqB, "T": T[(tv, n)]}, [wa, wb, wt])
    a, i, o = row(f"스퀴즈{wa:.0%}+자사주{wb:.0%}+타이밍{wt:.0%}(목표{tv:.0%},{n}일)", e)
    res.append((tv, n, wa, wb, wt, a[0], a[1], i[0], i[1], o[0], o[1]))
g = pd.DataFrame(res, columns="tv n wa wb wt CAGR MDD IS IS_MDD OOS OOS_MDD".split())
print("\nIS·OOS 모두 연 10% 이상:", ((g.IS >= .10) & (g.OOS >= .10)).sum(), "/", len(g))
g.to_csv("kr10_grid.csv", index=False)
pickle.dump({"A": eqA, "B": eqB, "T": T}, open("kr10_curves.pkl", "wb"))
