import numpy as np, pandas as pd
d = pd.read_csv('/tmp/bt/kospi_all.csv.gz', dtype={'code': str}, parse_dates=['Date'])
d['code'] = d.code.str.zfill(6)
C = d.pivot(index='Date', columns='code', values='Close'); O = d.pivot(index='Date', columns='code', values='Open')
idx = C.pop('KPI200') if 'KPI200' in C else None
C = C[[c for c in C.columns if c.isdigit() and c.endswith('0')]]; O = O[C.columns]
dU = C.diff(); up = dU.clip(lower=0).ewm(alpha=1/14, adjust=False, min_periods=14).mean(); dn = (-dU.clip(upper=0)).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
RSI = 100 - 100/(1+up/dn.replace(0, np.nan))
R = pd.read_csv('/tmp/work/events.csv', parse_dates=['dt'], dtype={'code': str}); R['good'] = (R.dd <= -.3) | R.rep
dates = C.index; Ci = C.values; Oi = O.values; Ri = RSI.values; col = {c: i for i, c in enumerate(C.columns)}

FB, FS = 0.00015, 0.00015 + 0.0018
Hi = None
def run(ev, size=1/7, maxpos=7, hold=10, rsi=70, stop=None, tp=None, trail=None, start='2015-01-01'):
    ev = ev.copy(); ev['i'] = dates.searchsorted(ev['dt'], side='right')
    byday = ev.groupby('i').code.apply(list).to_dict()
    cash = 1.0; pos = {}; eq = []; trades = []; npos = []
    for t in range(len(dates)):
        for c in list(pos):
            p = pos[c]; j = col[c]
            if p['exit']:
                px = Oi[t, j] if np.isfinite(Oi[t, j]) else Ci[t-1, j]
                cash += p['q'] * px * (1 - FS); trades.append(px / p['px'] - 1); del pos[c]
        val = cash + sum(p['q'] * (Ci[t-1, col[k]] if np.isfinite(Ci[t-1, col[k]]) else p['px']) for k, p in pos.items())
        for c in byday.get(t, []):
            j = col.get(c)
            if j is None or c in pos or len(pos) >= maxpos or not np.isfinite(Oi[t, j]) or Oi[t, j] <= 0: continue
            if Oi[t, j] > Ci[t-1, j] * 1.05: continue
            amt = min(val * size, cash)
            if amt < val * size * 0.3: continue
            q = amt / (Oi[t, j] * (1 + FB)); cash -= amt
            pos[c] = {'q': q, 'px': Oi[t, j], 'n': 0, 'exit': False, 'hi': Oi[t, j]}
        for c, p in pos.items():
            j = col[c]; p['n'] += 1; cl = Ci[t, j]
            if not np.isfinite(cl): continue
            p['hi'] = max(p['hi'], cl); r = cl / p['px'] - 1
            if p['n'] >= hold: p['exit'] = True
            if rsi and np.isfinite(Ri[t, j]) and Ri[t, j] > rsi: p['exit'] = True
            if stop and r <= -stop: p['exit'] = True
            if tp and r >= tp: p['exit'] = True
            if trail and cl <= p['hi'] * (1 - trail) and p['hi'] > p['px']: p['exit'] = True
        npos.append(len(pos))
        eq.append(cash + sum(p['q'] * (Ci[t, col[k]] if np.isfinite(Ci[t, col[k]]) else p['px']) for k, p in pos.items()))
    e = pd.Series(eq, index=dates); e = e[e.index >= start]; e = e / e.iloc[0]
    r = e.pct_change().dropna()
    def cagr(s): return (s.iloc[-1] / s.iloc[0]) ** (365.25 / (s.index[-1] - s.index[0]).days) - 1
    yr = e.resample('YE').last().pct_change(); yr.iloc[0] = e.resample('YE').last().iloc[0] - 1
    tr = np.array(trades); npos = np.array(npos[-len(e):])
    return dict(연=cagr(e), IS=cagr(e[:'2020-12-31']), OOS=cagr(e['2021-01-01':]), MDD=(e / e.cummax() - 1).min(),
                Sharpe=r.mean()/r.std()*np.sqrt(252), 거래=len(tr), 승률=(tr > 0).mean(), 평균=tr.mean(), 최악연=yr.min(), 평균보유=npos.mean(), 최대보유=npos.max())
def pr(nm, x):
    print(f"{nm:30s} 연 {x['연']:5.1%} | ~20 {x['IS']:5.1%} | 21~ {x['OOS']:5.1%} | MDD {x['MDD']:4.0%} | Sh {x['Sharpe']:.2f} | 거래 {x['거래']:4d} 승 {x['승률']:.0%} 평균 {x['평균']:+.2%} | 최악연 {x['최악연']:+.1%} | 보유 평균 {x['평균보유']:.1f}/최대 {x['최대보유']}")
G = R[R.good & ~(R.mcap >= 5e12)]
import sys
part = sys.argv[1]
if part == 'a':
    print('== 종목 수 (좋은 공시 & 5조 미만, 10일·RSI70)')
    pr('7종목 (각 1/7, 지금)', run(G))
    pr('10종목 (각 1/10)', run(G, 1/10, 10))
    for sz in [1/10, 1/15, 1/20, 1/30]:
        pr(f'다 담기 (한 종목 {sz:.0%}, 개수 무제한)', run(G, sz, 999))
    pr('다 담기 1/15 · 전체 공시(필터 없음)', run(R, 1/15, 999))
else:
    print('== 매도 규칙 (7종목)')
    for nm, kw in [('10일 + RSI>70 (지금)', {}), ('10일만', dict(rsi=None)), ('5일 + RSI70', dict(hold=5)), ('20일 + RSI70', dict(hold=20)),
                   ('10일 + RSI70 + 손절 -7%', dict(stop=.07)), ('10일 + RSI70 + 손절 -10%', dict(stop=.10)),
                   ('10일 + 익절 +10%', dict(rsi=None, tp=.10)), ('10일 + 익절 +7%', dict(rsi=None, tp=.07)),
                   ('20일 + 고점대비 -7% 추적손절', dict(rsi=None, hold=20, trail=.07)), ('20일 + RSI70 + 추적 -7%', dict(hold=20, trail=.07))]:
        pr(nm, run(G, **kw))
