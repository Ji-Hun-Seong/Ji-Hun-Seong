import numpy as np, pandas as pd
R = pd.read_csv('/tmp/work/events.csv', parse_dates=['dt'], dtype={'code': str})
IS = R.dt <= '2020-12-31'
def s(x):
    x = x.dropna(); n = len(x)
    if n < 3: return f"n{n}"
    return f"{x.mean():+.2%} 승{(x>0).mean():.0%} t{x.mean()/x.std()*np.sqrt(n):.1f} n{n}"
def row(nm, m):
    g = R[m]
    print(f"{nm:22s} 전체 {s(g.x10):32s} | ~2020 {s(g[g.dt<='2020-12-31'].x10):30s} | 2021~ {s(g[g.dt>'2020-12-31'].x10)}")
print('== 전체'); row('전체', R.x10.notna())
print('\n== 시가총액(공시 직전)')
for a, b, nm in [(0, 3e11, '<3천억'), (3e11, 1e12, '3천억~1조'), (1e12, 5e12, '1~5조'), (5e12, 1e20, '5조+')]:
    row(nm, R.mcap.between(a, b, inclusive='left'))
print('\n== 거래대금(20일 평균)')
for a, b, nm in [(0, 1e9, '<10억'), (1e9, 3e9, '10~30억'), (3e9, 2e10, '30~200억'), (2e10, 1e20, '200억+')]:
    row(nm, R.tv.between(a, b, inclusive='left'))
print('\n== PBR')
for a, b, nm in [(0, .5, '<0.5'), (.5, 1, '0.5~1'), (1, 2, '1~2'), (2, 99, '2+')]:
    row(nm, R.pbr.between(a, b, inclusive='left'))
print('\n== 매입 규모(시총 대비)')
for a, b, nm in [(0, .01, '<1%'), (.01, .03, '1~3%'), (.03, .05, '3~5%'), (.05, 9, '5%+')]:
    row(nm, R.amt.between(a, b, inclusive='left'))
print('\n== 52주 고점 대비')
for a, b, nm in [(-1, -.4, '-40% 이하'), (-.4, -.25, '-25~-40%'), (-.25, -.1, '-10~-25%'), (-.1, 1, '-10% 이내')]:
    row(nm, R.dd.between(a, b, inclusive='left'))
print('\n== 직전 20일 수익률')
for a, b, nm in [(-1, -.1, '-10% 이하'), (-.1, 0, '-10~0%'), (0, .1, '0~+10%'), (.1, 9, '+10%+')]:
    row(nm, R.ret20.between(a, b, inclusive='left'))
print('\n== 다음 날 시가 갭')
for a, b, nm in [(-1, 0, '갭 하락'), (0, .02, '0~2%'), (.02, .05, '2~5%'), (.05, 1, '5%+')]:
    row(nm, R.gap.between(a, b, inclusive='left'))
print('\n== 방식'); row('신탁', R.trust); row('직접취득', ~R.trust)
print('\n== 그 회사의 과거 자사주 공시 성과(사전 정보만)')
row('첫 공시', R.n_prev == 0)
row('과거 평균 > +2%', R.prev_mean > .02)
row('과거 평균 0~+2%', R.prev_mean.between(0, .02))
row('과거 평균 < 0', R.prev_mean < 0)
row('과거 2회+ & 평균>0', (R.n_prev >= 2) & (R.prev_mean > 0))
row('과거 2회+ & 평균<0', (R.n_prev >= 2) & (R.prev_mean < 0))

print('\n== 업종 (표본 15건+)')
g = R.groupby('sector').x10
t = pd.DataFrame(dict(n=g.size(), mean=g.mean(), win=g.apply(lambda x: (x > 0).mean()),
                      t=g.apply(lambda x: x.mean() / x.std() * np.sqrt(len(x)) if len(x) > 2 else 0)))
t = t[t.n >= 15].sort_values('mean', ascending=False)
print(t.to_string(formatters={'mean': '{:+.2%}'.format, 'win': '{:.0%}'.format, 't': '{:.1f}'.format}))

print('\n== 회사별 (자사주 공시 4건+)')
g = R.groupby(['code', 'name']).x10
t = pd.DataFrame(dict(n=g.size(), mean=g.mean(), med=g.median(), win=g.apply(lambda x: (x > 0).mean()),
                      last=R.groupby(['code', 'name']).dt.max().dt.strftime('%Y-%m')))
t = t[t.n >= 4].sort_values('mean', ascending=False)
t.to_csv('/tmp/work/by_company.csv')
fm = {'mean': '{:+.2%}'.format, 'med': '{:+.2%}'.format, 'win': '{:.0%}'.format}
print('회사 수', len(t)); print('-- 상위 20'); print(t.head(20).to_string(formatters=fm))
print('-- 하위 15'); print(t.tail(15).to_string(formatters=fm))
