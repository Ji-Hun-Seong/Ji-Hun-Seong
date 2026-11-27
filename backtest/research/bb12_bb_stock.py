"""자사주 공시 → 어떤 종목에서 잘 먹혔나 (2014-01 ~ 2026-10, 코스피 보통주)
진입: 공시일 다음 거래일 시가 / 청산: 10거래일 보유 종가 (기존 전략과 동일)
성과: 같은 기간 코스피 유니버스 동일가중 대비 초과수익(x10), 원수익(r10)
"""
import re, sys, numpy as np, pandas as pd
D = '/tmp/bt/'
d = pd.read_csv(D + 'kospi_all.csv.gz', dtype={'code': str}, parse_dates=['Date'])
d['code'] = d.code.str.zfill(6)
C = d.pivot(index='Date', columns='code', values='Close')
O = d.pivot(index='Date', columns='code', values='Open')
V = d.pivot(index='Date', columns='code', values='Volume')
keep = [c for c in C.columns if c.isdigit() and c.endswith('0')]
C, O, V = C[keep], O[keep], V[keep]
dates = C.index
TV = (C * V).rolling(20).mean()
RSI_up = C.diff().clip(lower=0).ewm(alpha=1/14).mean(); RSI_dn = (-C.diff().clip(upper=0)).ewm(alpha=1/14).mean()
RSI = 100 - 100 / (1 + RSI_up / RSI_dn)

f = pd.read_csv(D + 'dart_filings.csv.gz', dtype={'code': str, 'rcept_dt': str, 'rcept_no': str})
f['code'] = f.code.str.zfill(6); f['nm'] = f.report_nm.str.replace(r'\s+', '', regex=True)
f = f[~f.nm.str.startswith('[')]; f['dt'] = pd.to_datetime(f.rcept_dt)
bb = f[f.nm.str.contains(r'자기주식취득신탁계약체결결정|^(주요사항보고서\()?자기주식취득결정')].copy()
bb = bb.sort_values('dt').drop_duplicates(['code', 'rcept_dt'])
det = pd.read_csv(D + 'bb_detail.csv.gz', dtype={'code': str, 'rcept_no': str})
det = det.drop_duplicates('rcept_no').set_index('rcept_no')

names = pd.read_csv(D + 'kospi_all_members.csv', dtype={'code': str}, encoding='utf-8-sig')
names['code'] = names.code.str.zfill(6); NM = dict(zip(names.code, names.name))
ind = pd.read_csv('./toss-bot/data/industry_kr.csv', dtype={'code': str})
ind['code'] = ind.code.str.zfill(6); SEC = dict(zip(ind.code, ind.sector))

rows = []
for _, r in bb.iterrows():
    c = r.code
    if c not in C.columns: continue
    i = dates.searchsorted(r['dt'], side='right')
    if i + 10 > len(dates) or i < 260: continue
    o = O[c].iat[i]; pc = C[c].iat[i - 1]
    if not (np.isfinite(o) and o > 0 and np.isfinite(pc)): continue
    tv = TV[c].iat[i - 1]
    if not np.isfinite(tv) or tv < 3e8: continue
    cc = C.iloc[i + 9]; oo = O.iloc[i]
    u = (cc / oo - 1).replace([np.inf, -np.inf], np.nan).dropna().clip(-.9, 3).mean()
    r10 = C[c].iat[i + 9] / o - 1
    x = det.loc[r.rcept_no] if r.rcept_no in det.index else None
    mcap = pbr = amt = np.nan
    if x is not None and np.isfinite(x.shares) and x.shares > 0:
        mcap = x.shares * pc
        if np.isfinite(x.amount) and x.amount > 0: amt = x.amount / mcap
        if np.isfinite(x.equity) and x.equity > 0: pbr = mcap / x.equity
    rows.append(dict(dt=r['dt'], code=c, name=NM.get(c, r.flr_nm), sector=SEC.get(c, '?'),
        trust='신탁' in r.nm, r10=r10, x10=r10 - u, gap=o / pc - 1, tv=tv, mcap=mcap, pbr=pbr, amt=amt,
        dd=pc / C[c].iloc[i - 250:i].max() - 1, ret20=pc / C[c].iat[i - 21] - 1, rsi=RSI[c].iat[i - 1]))
R = pd.DataFrame(rows).sort_values('dt').reset_index(drop=True)
# 이 회사의 '이전' 자사주 공시 성과(사전 정보만 사용)
R['n_prev'] = R.groupby('code').cumcount()
R['prev_mean'] = R.groupby('code').x10.transform(lambda s: s.shift().expanding().mean())
R.to_csv('/tmp/work/events.csv', index=False)
print('표본', len(R), R.dt.min().date(), '~', R.dt.max().date())
