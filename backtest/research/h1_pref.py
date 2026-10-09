"""H1 우선주 괴리: BB/RSI를 (우선주/보통주) 비율에 적용."""
import sys
import numpy as np, pandas as pd
sys.path.insert(0, ".")
import engine
from engine import *
engine.BUY_COST = 0.00015 + 0.002          # 우선주는 호가가 얇아 슬리피지 0.2%로 보수적으로
engine.SELL_COST = 0.00015 + 0.002 + 0.002
piv, idx = load("/tmp/claude-0/btkr/kospi_all.csv.gz", "KPI200")
C, O, V = piv["Close"], piv["Open"], piv["Volume"]
prefs = [c for c in C.columns if not c.endswith("0") and (c[:5] + "0") in C.columns]
print("우선주-보통주 쌍:", len(prefs))
P = C[prefs]; Cm = C[[p[:5] + "0" for p in prefs]].set_axis(prefs, axis=1)
Rr = np.log(P / Cm)                                         # 로그 괴리 비율
N = 60
mid = Rr.rolling(N).mean(); sd = Rr.rolling(N).std()
pb = (Rr - (mid - 2 * sd)) / (4 * sd)
rsiR = Rr.apply(lambda s: rsi(np.exp(s), 14))
tvp = (P * V[prefs]).rolling(20).mean()
liquid = tvp > 3e8                                          # 우선주 20일 평균 거래대금 3억 원 이상
up_common = Cm > Cm.rolling(200).mean()

# 가설 자체 검정: 신호 후 h일 동안 '우선주 − 보통주' 초과수익(시장·기업 위험이 상쇄된 순수 괴리 회귀)
fwd = {}
for h in (5, 10, 20, 40):
    fwd[h] = (np.log(P.shift(-h) / P) - np.log(Cm.shift(-h) / Cm))
sig = (pb < 0) & (rsiR < 30) & liquid
anti = (pb > 1) & (rsiR > 70) & liquid
for nm, lo, hi in [("IS", START, IS_END), ("OOS", IS_END, None)]:
    s = sig.loc[lo:hi]; a = anti.loc[lo:hi]
    print(f"\n[{nm}] 신호 수: 우선주 저평가 {int(s.values.sum())}회, 고평가 {int(a.values.sum())}회")
    for h, F in fwd.items():
        F = F.loc[lo:hi]
        base = F.where(liquid.loc[lo:hi]).stack().mean()
        x = F.where(s).stack(); y = F.where(a).stack()
        print(f"  {h:2d}일 후 우선주−보통주: 저평가신호 {x.mean():+.2%} (승률 {(x>0).mean():.0%}, n={len(x)}) | 고평가신호 {y.mean():+.2%} | 평소 {base:+.2%}")

# 포트폴리오: 저평가 신호에서 우선주 매수, 괴리가 중심선(%b>0.5)으로 돌아오면 매도
f = {"C": P, "O": O[prefs], "regime": idx > idx.rolling(200).mean(), "idx": idx}
for regime in (False, True):
    for park in (False, True):
        eq, ex, tr = simulate(f, entry=sig, score=rsiR, exit_sig=pb > 0.5, max_pos=8, hold=40, regime=regime, park=park)
        m = split_metrics(eq, ex, tr)
        print(f"우선주 괴리 포트폴리오 regime={regime} park={park} | " + " | ".join(f"{k} {m[k]['CAGR']:+.1%} MDD {m[k]['MDD']:+.1%} Sh {m[k]['Sharpe']:.2f}" for k in m) +
              f" | N{m['ALL'].get('N',0)} 승률 {m['ALL'].get('Win',0):.0%} 건당 {m['ALL'].get('AvgTr',0):+.2%} 노출 {m['ALL']['Expo']:.0%}")
# 같은 종목, 같은 보유기간 무작위 진입(플라시보)
freq = sig.loc[START:].values.mean(); res = []
for seed in range(20):
    rnd = pd.DataFrame(np.random.default_rng(seed).random(P.shape) < freq, index=P.index, columns=P.columns) & liquid
    eq, ex, tr = simulate(f, entry=rnd, score=rsiR * 0, exit_sig=pb > 0.5, max_pos=8, hold=40)
    res.append(metrics(eq)["CAGR"])
print(f"플라시보 우선주 무작위 진입: CAGR 평균 {np.mean(res):+.1%}, 최대 {np.max(res):+.1%}")
