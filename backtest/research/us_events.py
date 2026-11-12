import numpy as np, pandas as pd
d = pd.read_csv('/tmp/bt/us_prices.csv.gz', parse_dates=['Date'])
C = d.pivot(index='Date', columns='code', values='Close'); O = d.pivot(index='Date', columns='code', values='Open'); V = d.pivot(index='Date', columns='code', values='Volume')
SPY = C['SPY']; SPYO = O['SPY']
for X_ in (C, O, V): X_.drop(columns=['SPY'], inplace=True)
dates = C.index
dU = C.diff(); up = dU.clip(lower=0).ewm(alpha=1/14, adjust=False, min_periods=14).mean(); dn = (-dU.clip(upper=0)).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
RSI = 100 - 100/(1+up/dn.replace(0, np.nan))
MA200 = C.rolling(200).mean(); V20 = V.rolling(20).mean().shift(1); HI = C.rolling(250, min_periods=120).max()
ret = C.pct_change(); mkt = ret.mean(axis=1)             # 유니버스 동일가중
E = pd.read_csv('/tmp/usev/us_yfearn.csv.gz'); E = E.dropna(subset=['act'])
t = pd.to_datetime(E.dt.str.slice(0, 19)); E['day'] = t.dt.normalize(); E['pre'] = (t.dt.hour * 60 + t.dt.minute) < 9 * 60 + 30
E = E[(E.day >= '2014-06-01') & E.code.isin(C.columns)].drop_duplicates(['code', 'day'])
DV = pd.read_csv('/tmp/usev/us_div.csv.gz', parse_dates=['exdate']).sort_values('exdate')
dvg = {c: g for c, g in DV.groupby('code')}
col = {c: i for i, c in enumerate(C.columns)}
Ca, Oa, Va = C.values, O.values, V.values; Ra = ret.values; Ma = mkt.values; cum = np.nancumsum(np.log1p(np.nan_to_num(Ma)))
rows = []
for r in E.itertuples():
    j = col[r.code]
    i = dates.searchsorted(r.day, side='left' if r.pre else 'right')     # 반응일 R
    if i < 250 or i + 62 >= len(dates) or not np.isfinite(Ca[i, j]) or not np.isfinite(Oa[i + 1, j]): continue
    b = i + 1; o = Oa[b, j]
    def x(h):
        c_ = Ca[b + h - 1, j]
        return (c_ / o - 1) - (np.exp(cum[b + h - 1] - cum[b - 1]) - 1) if np.isfinite(c_) else np.nan   # 유니버스는 종가~종가 근사
    g = dvg.get(r.code); raised = False; pays = False
    if g is not None:
        past = g[g.exdate <= dates[i]]
        if len(past) >= 5:
            pays = (dates[i] - past.exdate.iloc[-1]).days < 200
            raised = pays and past['div'].iloc[-1] > past['div'].iloc[-5] * 1.03
    rows.append(dict(code=r.code, dt=dates[i], i=i, surp=r.surp, est=r.est, act=r.act,
        react=Ra[i, j] - Ma[i], gap=Oa[i, j] / Ca[i - 1, j] - 1, body=Ca[i, j] / Oa[i, j] - 1,
        vr=Va[i, j] / V20.values[i, j], up200=Ca[i, j] > MA200.values[i, j], hi=Ca[i, j] / HI.values[i, j] - 1,
        pre60=Ca[i - 1, j] / Ca[i - 61, j] - 1, raised=raised, pays=pays, x5=x(5), x10=x(10), x20=x(20), x60=x(60)))
R = pd.DataFrame(rows); R.to_pickle('US.pkl')
def s(v):
    v = v.dropna(); n = len(v); return f"{v.mean():+.2%}(t{v.mean()/v.std()*np.sqrt(n) if n > 2 else 0:.1f},n{n},승{(v > 0).mean():.0%})"
print('이벤트', len(R), R.dt.min().date(), R.dt.max().date(), '서프라이즈 있음', R.surp.notna().mean().round(2))
IS = R.dt <= '2020-12-31'
F = {'전체': R.x10.notna(), '서프>0': R.surp > 0, '서프>5%': R.surp > 5, '서프>15%': R.surp > 15, '서프<0': R.surp < 0,
     '반응>+3%': R.react > .03, '반응>+5%': R.react > .05, '반응>+8%': R.react > .08, '반응<-5%': R.react < -.05,
     '서프>0&반응>3%': (R.surp > 0) & (R.react > .03), '서프>5&반응>5%': (R.surp > 5) & (R.react > .05),
     '서프>0&반응>3%&거래량2배': (R.surp > 0) & (R.react > .03) & (R.vr > 2),
     '서프>0&반응>3%&200일선위': (R.surp > 0) & (R.react > .03) & R.up200,
     '서프>0&반응>3%&신고가-5%내': (R.surp > 0) & (R.react > .03) & (R.hi > -.05),
     '서프>0&반응>3%&양봉': (R.surp > 0) & (R.react > .03) & (R.body > 0),
     '서프>0&반응>3%&배당증액': (R.surp > 0) & (R.react > .03) & R.raised,
     '서프>0&배당증액': (R.surp > 0) & R.raised, '배당증액(전체)': R.raised, '무배당': ~R.pays,
     '서프>0&반응<-5%(좋은데 급락)': (R.surp > 0) & (R.react < -.05)}
for h in ['x10', 'x20', 'x60']:
    print('==', h)
    for k, m in F.items():
        g = R[m]; print(f"{k:26s} IS {s(g[g.dt <= '2020-12-31'][h])} | OOS {s(g[g.dt > '2020-12-31'][h])}")
