import numpy as np, pandas as pd, io, subprocess
exec(open('sell.py').read().split("G=R[R.good]")[0])
B = pd.read_csv('/tmp/bb/bb_detail.csv.gz', dtype={'code': str, 'rcept_dt': str, 'rcept_no': str}); B['code'] = B.code.str.zfill(6)
B['dt'] = pd.to_datetime(B.rcept_dt)
VU = pd.read_csv('/tmp/bb/bb_valueup.csv.gz', dtype={'code': str, 'rcept_dt': str}); VU['code'] = VU.code.str.zfill(6); VU['dt'] = pd.to_datetime(VU.rcept_dt)
X = R.merge(B[['code', 'dt', 'amount', 'shares_plan', 'burn', 'shares', 'equity']], on=['code', 'dt'], how='left')
pc = []
for _, r in X.iterrows():
    i = dates.searchsorted(r['dt'], side='right'); pc.append(Ci[i-1, col[r['code']]])
X['pc'] = pc
X['mcap'] = X.shares * X.pc
amt = X.amount.where(X.amount > 0, X.shares_plan * X.pc)
X['size'] = amt / X.mcap
X['pbr'] = X.mcap / X.equity.where(X.equity > 0)
def pledge(r):
    v = VU[(VU.code == r['code']) & (VU.dt < r['dt']) & (VU.dt >= r['dt'] - pd.Timedelta(days=730)) & (VU.pledge_year > 0)]
    return v.pledge_year.max() / r['mcap'] if len(v) and r['mcap'] > 0 else np.nan
X['pledge'] = X.apply(pledge, axis=1)
X.to_pickle('X.pkl')
print('금액 있음', X['size'].notna().mean().round(2), 'PBR 있음', X.pbr.notna().mean().round(2), '밸류업 약속', X.pledge.notna().sum())
print(X[['size','pbr']].describe().round(3))
def s(x):
    x = x.dropna(); n = len(x); return f"{x.mean():+.2%}(t{x.mean()/x.std()*np.sqrt(n) if n>2 else 0:.1f},n{n},승{(x>0).mean():.0%})"
IS = X.dt <= '2020-12-31'
F = {'전체': X.x10.notna(), '기존 좋음(낙폭/재매입)': X.good,
     '규모≥3%': X['size'] >= .03, '규모 1~3%': X['size'].between(.01, .03), '규모<1%': X['size'] < .01,
     'PBR<0.5': X.pbr < .5, 'PBR 0.5~1': X.pbr.between(.5, 1), 'PBR≥1': X.pbr >= 1,
     '소각 목적': X.burn == True, '소각 아님': X.burn == False,
     '밸류업 약속≥3% 이행': X.pledge >= .03,
     '저PBR(<1)&규모≥2%': (X.pbr < 1) & (X['size'] >= .02),
     '저PBR(<1)&소각': (X.pbr < 1) & (X.burn == True),
     '기존좋음 OR 규모≥3%': X.good | (X['size'] >= .03),
     '기존좋음 & PBR<1': X.good & (X.pbr < 1)}
for k, m in F.items():
    g = X[m]; print(f"{k:22s} IS {s(g[g.dt<='2020-12-31'].x10)} | OOS {s(g[g.dt>'2020-12-31'].x10)}")
print()
for k in ['전체', '기존 좋음(낙폭/재매입)', '규모≥3%', 'PBR<0.5', 'PBR 0.5~1', '소각 목적', '저PBR(<1)&규모≥2%', '기존좋음 OR 규모≥3%', '기존좋음 & PBR<1']:
    for sl in [7, 10]:
        x = run(X[F[k]], slots=sl); print(f"{k:22s} {sl}종목 연 {x['연']:.1%} IS {x['IS']:.1%} OOS {x['OOS']:.1%} MDD {x['MDD']:.0%} Sharpe {x['Sharpe']:.2f} 거래 {x['거래']} 최악연 {x['최악연']:+.1%}")
