import numpy as np, pandas as pd
exec(open('us_ev.py').read().split("E = pd.read_csv")[0])
R = pd.read_pickle('US.pkl'); col = {c: i for i, c in enumerate(C.columns)}
Ca, Oa, Ri = C.values, O.values, RSI.values; spy = SPY.values; spyo = SPYO.values
FEE = 0.0015
def run(ev, slots=10, hold=60, rx=999, park=False, stop=None):
    byday = ev.sort_values('react', ascending=False).groupby('i').code.apply(list).to_dict()
    cash = 1.0; pk = 0.0; pos = {}; eq = []; tr = []
    for t in range(250, len(dates)):
        for c in list(pos):
            p = pos[c]; j = col[c]
            if p['exit']:
                px = Oa[t, j] if np.isfinite(Oa[t, j]) else p['last']
                cash += p['q'] * px * (1 - FEE); tr.append(px / p['px'] - 1); del pos[c]
        for c in byday.get(t - 1, []):                      # 반응일 다음 날 시가 매수
            j = col[c]
            if c in pos or len(pos) >= slots or not np.isfinite(Oa[t, j]): continue
            val = cash + pk * spyo[t] + sum(p['q'] * p['last'] for p in pos.values())
            amt = val / slots
            if park and cash < amt:
                need = min(amt - cash, pk * spyo[t]); pk -= need / spyo[t]; cash += need * (1 - 0.0005)
            amt = min(amt, cash)
            if amt <= 0: continue
            pos[c] = {'q': amt / (Oa[t, j] * (1 + FEE)), 'px': Oa[t, j], 'n': 0, 'exit': False, 'last': Oa[t, j]}; cash -= amt
        for c, p in pos.items():
            j = col[c]; p['n'] += 1
            if np.isfinite(Ca[t, j]): p['last'] = Ca[t, j]
            if p['n'] >= hold or (np.isfinite(Ri[t, j]) and Ri[t, j] > rx and p['n'] >= 3) or (stop and p['last'] / p['px'] - 1 < -stop): p['exit'] = True
        if park and cash > 0.001:
            pk += cash * (1 - 0.0005) / spy[t]; cash = 0
        eq.append(cash + pk * spy[t] + sum(p['q'] * p['last'] for p in pos.values()))
    e = pd.Series(eq, index=dates[250:]); e = e / e.iloc[0]; r = e.pct_change().dropna()
    cg = lambda s_: (s_.iloc[-1] / s_.iloc[0]) ** (365.25 / (s_.index[-1] - s_.index[0]).days) - 1
    yr = e.resample('YE').last().pct_change().dropna(); t_ = np.array(tr)
    return f"연 {cg(e):.1%} IS {cg(e[:'2020-12-31']):.1%} OOS {cg(e['2021-01-01':]):.1%} MDD {(e/e.cummax()-1).min():.0%} Sh {r.mean()/r.std()*np.sqrt(252):.2f} 거래 {len(t_)} 승 {(t_>0).mean():.0%} 평균 {t_.mean():+.1%} 최악연 {yr.min():+.0%}"
s_ = SPY[dates[250]:]; print('SPY 보유', f"연 {(s_.iloc[-1]/s_.iloc[0])**(365.25/(s_.index[-1]-s_.index[0]).days)-1:.1%} MDD {(s_/s_.cummax()-1).min():.0%}")
A = R[(R.surp > 5) & (R.react > .05)]; B = R[(R.surp > 15) & (R.react > .05)]; G = R[R.react > .08]
for nm, ev in [('서프>5&반응>5%', A), ('서프>15&반응>5%', B), ('반응>8%', G)]:
    for kw in [dict(), dict(rx=70), dict(rx=80), dict(hold=20), dict(hold=20, rx=70), dict(park=True), dict(park=True, rx=80), dict(hold=120, park=True)]:
        print(f"{nm:14s} {str(kw):34s}", run(ev, **kw))
