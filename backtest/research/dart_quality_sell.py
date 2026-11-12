import numpy as np, pandas as pd
d = pd.read_csv('/tmp/bt/kospi_all.csv.gz', dtype={'code': str}, parse_dates=['Date'])
d['code'] = d.code.str.zfill(6)
C = d.pivot(index='Date', columns='code', values='Close'); O = d.pivot(index='Date', columns='code', values='Open')
idx = C.pop('KPI200') if 'KPI200' in C else None
C = C[[c for c in C.columns if c.isdigit() and c.endswith('0')]]; O = O[C.columns]
dU = C.diff(); up = dU.clip(lower=0).ewm(alpha=1/14, adjust=False, min_periods=14).mean(); dn = (-dU.clip(upper=0)).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
RSI = 100 - 100/(1+up/dn.replace(0, np.nan))
R = pd.read_pickle('R.pkl'); R['good'] = (R.dd <= -.3) | R.rep
dates = C.index; Ci = C.values; Oi = O.values; Ri = RSI.values; col = {c: i for i, c in enumerate(C.columns)}
FB, FS = 0.00015, 0.00015 + 0.0018
def run(ev, slots=10, hold=10, rx=70):
    ev = ev.copy(); ev['i'] = dates.searchsorted(ev['dt'], side='right')
    byday = ev.groupby('i').code.apply(list).to_dict()
    cash = 1.0; pos = {}; eq = []; trades = []
    for t in range(len(dates)):
        # 매도: 전날 신호(보유일 도달 or RSI>70) → 오늘 시가
        for c in list(pos):
            p = pos[c]; j = col[c]
            if p['exit']:
                px = Oi[t, j] if np.isfinite(Oi[t, j]) else Ci[t-1, j]
                cash += p['q'] * px * (1 - FS); trades.append(px / p['px'] - 1); del pos[c]
        for c in byday.get(t, []):
            j = col.get(c)
            if j is None or c in pos or len(pos) >= slots or not np.isfinite(Oi[t, j]) or Oi[t, j] <= 0: continue
            if Oi[t, j] > Ci[t-1, j] * 1.05: continue      # 갭 +5% 초과 추격 안 함
            val = cash + sum(p['q'] * (Ci[t, col[k]] if np.isfinite(Ci[t, col[k]]) else p['px']) for k, p in pos.items())
            amt = min(val / slots, cash)
            if amt <= 0: continue
            q = amt / (Oi[t, j] * (1 + FB)); cash -= amt
            pos[c] = {'q': q, 'px': Oi[t, j], 'n': 0, 'exit': False}
        for c, p in pos.items():
            j = col[c]; p['n'] += 1
            if p['n'] >= hold or (np.isfinite(Ri[t, j]) and Ri[t, j] > rx): p['exit'] = True
        eq.append(cash + sum(p['q'] * (Ci[t, col[k]] if np.isfinite(Ci[t, col[k]]) else p['px']) for k, p in pos.items()))
    e = pd.Series(eq, index=dates); e = e[e.index >= '2015-01-01']; e = e / e.iloc[0]
    yrs = (e.index[-1] - e.index[0]).days / 365.25; r = e.pct_change().dropna()
    def cagr(s): return (s.iloc[-1] / s.iloc[0]) ** (365.25 / (s.index[-1] - s.index[0]).days) - 1
    IS, OOS = e[:'2020-12-31'], e['2021-01-01':]
    yr = e.resample('YE').last().pct_change(); yr.iloc[0] = e.resample('YE').last().iloc[0] - 1
    tr = np.array(trades)
    return dict(연=cagr(e), IS=cagr(IS), OOS=cagr(OOS), MDD=(e / e.cummax() - 1).min(), Sharpe=r.mean()/r.std()*np.sqrt(252),
                거래=len(tr), 승률=(tr > 0).mean(), 평균=tr.mean(), 최악연=yr.min(), yearly=yr)

G=R[R.good]
for nm,kw in [("10일+RSI70(지금)",{}),("10일, RSI 익절 없음",dict(rx=999)),("10일+RSI75",dict(rx=75)),("10일+RSI65",dict(rx=65)),
              ("5일+RSI70",dict(hold=5)),("20일+RSI70",dict(hold=20)),("20일, RSI 없음",dict(hold=20,rx=999))]:
    x=run(G,slots=7,**kw); print(f"{nm:18s} 연 {x['연']:.1%} IS {x['IS']:.1%} OOS {x['OOS']:.1%} MDD {x['MDD']:.0%} Sharpe {x['Sharpe']:.2f} 승률 {x['승률']:.0%} 평균 {x['평균']:+.2%} 최악연 {x['최악연']:+.1%}")
