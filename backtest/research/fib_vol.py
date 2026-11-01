"""5차: RSI + 볼린저 + 피보나치 + 거래량 변화 스윙 (토스 자동매매용) — 시점별 거래대금 상위 200 유니버스"""
import sys, itertools
import numpy as np, pandas as pd
sys.path.insert(0, sys.argv[2] if len(sys.argv) > 2 else ".")
from engine import *
from numpy.lib.stride_tricks import sliding_window_view as swv

piv, idx = load(sys.argv[1], "KPI200")
keep = [c for c in piv["Close"].columns if c.endswith("0")]
piv = {k: v[keep] for k, v in piv.items()}
f = features(piv, idx); C, H, L, V = f["C"], piv["High"], piv["Low"], piv["Volume"]
age = C.notna().cumsum()
me = f["tv"].where(age > 250).resample("ME").last().rank(axis=1, ascending=False)
uni = (me <= 200).shift(1).reindex(C.index, method="ffill").fillna(False).astype(bool)

# 피보나치: 최근 N일 스윙(저점 → 이후 고점). 되돌림 r = (고점-종가)/(고점-저점)
def fib(N=60):
    h, l = H.ffill().values, L.ffill().values
    T, K = h.shape
    hi = np.full((T, K), np.nan); lo = np.full((T, K), np.nan); ok = np.zeros((T, K), bool)
    wh, wl = swv(np.nan_to_num(h, nan=-1), N, axis=0), swv(np.nan_to_num(l, nan=1e18), N, axis=0)   # (T-N+1, K, N)
    ia = wh.argmax(axis=2); hv = np.take_along_axis(wh, ia[..., None], 2)[..., 0]
    # 고점 이전 구간의 최저점
    ar = np.arange(N)[None, None, :]
    wl_m = np.where(ar <= ia[..., None], wl, 1e18)
    lv = wl_m.min(axis=2)
    hi[N - 1:], lo[N - 1:] = hv, lv
    ok[N - 1:] = (ia >= 5) & (ia <= N - 3)        # 고점이 창 끝에 붙어있지 않음(되돌림 진행 중), 저점→고점 최소 5일
    hi, lo = pd.DataFrame(hi, C.index, C.columns), pd.DataFrame(lo, C.index, C.columns)
    r = (hi - C) / (hi - lo)
    amp = hi / lo - 1
    return r.where(ok & (lo < 1e17)), hi, lo, amp

vr = V / V.rolling(20).mean()                     # 거래량 변화(20일 평균 대비)
upday = C > C.shift(1)
rsi_up = f["rsi14"] > f["rsi14"].shift(1)
trend = (C > f["ma200"]) & (f["ma50"] > f["ma200"])

def line(name, m):
    a, i, o = m["ALL"], m["IS"], m["OOS"]
    print(f"{name:34s} | {a['CAGR']:+.1%} MDD{a['MDD']:+.1%} Sh{a['Sharpe']:.2f} 노출{a.get('Expo',1):.0%} | IS {i['CAGR']:+.1%} Sh{i['Sharpe']:.2f} | OOS {o['CAGR']:+.1%} Sh{o['Sharpe']:.2f} MDD{o['MDD']:+.1%} | N{a.get('N',0)} 승{a.get('Win',0):.0%} {a.get('AvgTr',0):+.2%} {a.get('Days',0):.0f}일", flush=True)

bench = idx[idx.index >= START]
line("코스피200 지수", split_metrics(bench, pd.Series(1.0, index=bench.index)))

FIB = {N: fib(N) for N in (40, 60, 120)}

def pullback(N=60, zlo=0.382, zhi=0.618, rmax=50, vmin=1.5, amp=0.15, mp=10, hold=20, xr=70, regime=True):
    r, hi, lo, a = FIB[N]
    e = trend & (r >= zlo) & (r <= zhi) & (a >= amp) & (f["rsi14"] < rmax) & rsi_up & (f["pb"] < 0.5) & (vr >= vmin) & upday & uni
    stop_line = hi - (hi - lo) * 0.786                       # 78.6% 되돌림 깨지면 손절
    x = (f["rsi14"] > xr) | (C > f["up"]) | (C < stop_line.shift(1)) | (C >= hi.shift(1))
    return dict(entry=e, score=-vr, exit_sig=x, max_pos=mp, hold=hold, regime=regime)

def breakout(N=60, vmin=2.0, rmin=60, mp=10, xr=40, sq=0.2):
    r, hi, lo, a = FIB[N]
    prevhi = H.rolling(N).max().shift(1)
    e = (C > prevhi) & (C > f["up"]) & (f["rsi14"] > rmin) & (vr >= vmin) & (f["ma50"] > f["ma200"]) & uni
    if sq is not None:
        e &= f["bw_q"].rolling(10).min() < sq
    return dict(entry=e, score=f["mom"], ascending=False, exit_sig=f["rsi14"] < xr, max_pos=mp, hold=250, regime=True)

def meanrev(vmin=1.5, mp=10, N=120):
    r, hi, lo, a = FIB[N]
    e = trend & (f["pb"] < 0) & (f["rsi14"] < 35) & (r >= 0.5) & (r <= 0.786) & (vr >= vmin) & uni
    x = (C >= f["mid"]) | (f["rsi14"] > 55)
    return dict(entry=e, score=f["rsi14"], exit_sig=x, max_pos=mp, hold=15, stop=0.10, regime=True)

print("\n[대표 설정]")
for name, kw in [("A 피보 눌림목(38~62%)+거래량", pullback()), ("A' 거래량 조건 없음", pullback(vmin=0)),
                 ("A'' 시장필터 없음", pullback(regime=False)),
                 ("B 피보 돌파(60일 고점)+거래량2배", breakout()), ("B' 스퀴즈 조건 없음", breakout(sq=None)),
                 ("B'' 거래량 조건 없음", breakout(vmin=0)),
                 ("C 과매도 반등(BB하단·피보50~79%)", meanrev())]:
    eq, ex, tr = simulate(f, **kw); line(name, split_metrics(eq, ex, tr))
    if name.startswith(("A ", "B ")):
        freq = kw["entry"].loc[START:].values.mean(); res = []
        for seed in range(10):
            rnd = pd.DataFrame(np.random.default_rng(seed).random(C.shape) < freq, index=C.index, columns=C.columns) & uni & C.notna()
            k = dict(kw); k["entry"] = rnd; k["score"] = f["mom"] * 0
            m = metrics(simulate(f, **k)[0]); res.append(m["CAGR"])
        print(f"   └ 무작위 진입(같은 빈도·청산) 10회 평균 {np.mean(res):+.1%}, 최대 {np.max(res):+.1%}")

print("\n[그리드: 피보 눌림목]")
rows = []
for N, z, rmax, vmin, mp in itertools.product([40, 60, 120], [(0.236, 0.5), (0.382, 0.618), (0.5, 0.786)], [45, 55], [1.0, 1.5, 2.0], [10, 15]):
    m = split_metrics(*simulate(f, **pullback(N, z[0], z[1], rmax, vmin, mp=mp))[:2])
    rows.append((N, z, rmax, vmin, mp, m["ALL"]["CAGR"], m["ALL"]["Sharpe"], m["ALL"]["MDD"], m["IS"]["CAGR"], m["IS"]["Sharpe"], m["OOS"]["CAGR"], m["OOS"]["Sharpe"]))
g = pd.DataFrame(rows, columns="N z rmax vmin mp CAGR Sh MDD IS IS_Sh OOS OOS_Sh".split())
print(f"{len(g)}개: CAGR 중앙값 {g.CAGR.median():+.1%} (하위10% {g.CAGR.quantile(.1):+.1%}, 상위10% {g.CAGR.quantile(.9):+.1%}), Sharpe 중앙값 {g.Sh.median():.2f}")
gs = g.sort_values("IS_Sh", ascending=False)
print("IS 상위 1/3의 OOS 중앙값 %+.1f%% Sh %.2f" % (gs.head(len(g)//3).OOS.median()*100, gs.head(len(g)//3).OOS_Sh.median()))
print(gs.head(5).to_string())
for col in ["N", "z", "vmin"]:
    print(col, g.groupby(col)[["CAGR", "Sh", "OOS"]].median().round(3).to_dict("index"))

print("\n[그리드: 피보 돌파]")
rows = []
for N, vmin, rmin, sq, mp in itertools.product([40, 60, 120], [1.0, 1.5, 2.0, 3.0], [55, 60, 65], [None, 0.2, 0.3], [10, 15]):
    m = split_metrics(*simulate(f, **breakout(N, vmin, rmin, mp, sq=sq))[:2])
    rows.append((N, vmin, rmin, sq, mp, m["ALL"]["CAGR"], m["ALL"]["Sharpe"], m["ALL"]["MDD"], m["IS"]["CAGR"], m["IS"]["Sharpe"], m["OOS"]["CAGR"], m["OOS"]["Sharpe"]))
g2 = pd.DataFrame(rows, columns="N vmin rmin sq mp CAGR Sh MDD IS IS_Sh OOS OOS_Sh".split())
print(f"{len(g2)}개: CAGR 중앙값 {g2.CAGR.median():+.1%} (하위10% {g2.CAGR.quantile(.1):+.1%}, 상위10% {g2.CAGR.quantile(.9):+.1%}), Sharpe 중앙값 {g2.Sh.median():.2f}")
gs2 = g2.sort_values("IS_Sh", ascending=False)
print("IS 상위 1/3의 OOS 중앙값 %+.1f%% Sh %.2f" % (gs2.head(len(g2)//3).OOS.median()*100, gs2.head(len(g2)//3).OOS_Sh.median()))
print(gs2.head(5).to_string())
for col in ["N", "vmin", "sq"]:
    print(col, g2.groupby(col, dropna=False)[["CAGR", "Sh", "OOS"]].median().round(3).to_dict("index"))
g.to_csv("fib_grid_pullback.csv", index=False); g2.to_csv("fib_grid_breakout.csv", index=False)
print("데이터 끝:", C.index[-1].date())
