"""8차: 좋은 자사주 공시 조건(재매입·52주 낙폭·밸류업·소각 이력). 데이터: bt-data-kr, bt-data-dart 브랜치를 /tmp/bt 에 풀어서 실행."""
import re, numpy as np, pandas as pd
d = pd.read_csv('/tmp/bt/kospi_all.csv.gz', dtype={'code': str}, parse_dates=['Date'])
d['code'] = d.code.str.zfill(6)
C = d.pivot(index='Date', columns='code', values='Close'); O = d.pivot(index='Date', columns='code', values='Open')
V = d.pivot(index='Date', columns='code', values='Volume')
for k in [c for c in C.columns if not c.isdigit() or not c.endswith('0')]:
    C.pop(k); O.pop(k); V.pop(k)
dates = C.index
TV = (C * V).rolling(20).mean()
f = pd.read_csv('/tmp/bt/dart_filings.csv.gz', dtype={'code': str, 'rcept_dt': str})
f['code'] = f.code.str.zfill(6); f['nm'] = f.report_nm.str.replace(r'\s+', '', regex=True)
f = f[~f.nm.str.startswith('[')]; f['dt'] = pd.to_datetime(f.rcept_dt)
bb = f[f.nm.str.contains(r'자기주식취득신탁계약체결결정|^(주요사항보고서\()?자기주식취득결정')].copy()
bb = bb.sort_values('dt').drop_duplicates(['code', 'rcept_dt'])
vu = f[f.nm.str.contains('기업가치제고계획')]; sk = f[f.nm.str.contains('주식소각결정')]
def prior(g, code, dt, days, same_ok=True):
    x = g[(g.code == code) & (g.dt <= dt) & (g.dt >= dt - pd.Timedelta(days=days))]
    return len(x) > 0
# 유니버스 평균 수익(동일가중)
rows = []
for _, r in bb.iterrows():
    c = r.code
    if c not in C.columns: continue
    i = dates.searchsorted(r['dt'], side='right')   # 다음 거래일
    if i + 20 >= len(dates): continue
    o = O[c].iat[i]; 
    if not np.isfinite(o) or o <= 0: continue
    tv = TV[c].iat[i - 1]
    if not np.isfinite(tv) or tv < 3e8: continue
    def xr(h):
        cc = C.iloc[i + h - 1]; oo = O.iloc[i]
        u = (cc / oo - 1).replace([np.inf, -np.inf], np.nan).dropna()
        return C[c].iat[i + h - 1] / o - 1 - u.clip(-.9, 3).mean()
    rows.append(dict(dt=r['dt'], code=c, x10=xr(10), x20=xr(20), tv=tv,
        vu=prior(vu, c, r['dt'], 365), vu_same=prior(vu, c, r['dt'], 3),
        sk2y=prior(sk, c, r['dt'] - pd.Timedelta(days=1), 730), sk_same=prior(sk, c, r['dt'], 0),
        rep=prior(bb[bb.dt < r['dt']], c, r['dt'] - pd.Timedelta(days=1), 365),
        dd=C[c].iat[i - 1] / C[c].iloc[max(0, i - 250):i].max() - 1,
        trust='신탁' in r['nm']))
R = pd.DataFrame(rows); R.to_pickle('/tmp/work/R.pkl')
def s(x):
    x = x.dropna(); n = len(x)
    return f"{x.mean():+.2%} (n{n}, 승{(x>0).mean():.0%}, t{x.mean()/x.std()*np.sqrt(n) if n>2 else 0:.1f})"
IS = R.dt <= '2020-12-31'
print('전체', s(R.x10), '| IS', s(R[IS].x10), '| OOS', s(R[~IS].x10))
for nm, m in [('밸류업 공시 1년 내', R.vu), ('밸류업 없음(2024-06~)', (~R.vu) & (R.dt >= '2024-06-01')),
              ('밸류업 같은 날±3일', R.vu_same), ('2년 내 소각 이력', R.sk2y), ('소각 이력 없음', ~R.sk2y),
              ('같은 날 소각결정', R.sk_same), ('1년 내 재매입', R.rep), ('첫 매입(1년)', ~R.rep),
              ('고점 -30% 이하', R.dd < -.3), ('고점 -15~-30%', R.dd.between(-.3, -.15)), ('고점 -15% 이내', R.dd > -.15),
              ('신탁', R.trust), ('직접취득', ~R.trust)]:
    g = R[m]
    print(f"{nm:16s} 10일 IS {s(g[g.dt<='2020-12-31'].x10)} | OOS {s(g[g.dt>'2020-12-31'].x10)} | 20일 전체 {s(g.x20)}")
