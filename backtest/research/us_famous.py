"""10차: 인터넷에서 유명한 자동매매 전략(레버리지 없음) — 미국 ETF, 2005~2026. 데이터: bt-data-etf → /tmp/etf"""
import numpy as np, pandas as pd
d = pd.read_csv('/tmp/etf/etf_prices.csv.gz', parse_dates=['Date'])
P = lambda f: d.pivot(index='Date', columns='code', values=f)
C, O, H, L = P('Close'), P('Open'), P('High'), P('Low')
us = C['SPY'].dropna().index; C, O, H, L = [x.reindex(us).ffill() for x in (C, O, H, L)]
START = '2005-01-03'; COST = 0.001
ret = C.pct_change().fillna(0)
def from_w(W, lag=1):
    """W: 일별 목표 비중(종가에 계산) → lag일 뒤 종가부터 적용. 회전 비용 차감."""
    W = W.reindex(us).ffill().fillna(0).shift(lag).fillna(0)
    r = (W * ret[W.columns]).sum(axis=1) - W.diff().abs().sum(axis=1).fillna(0) * COST
    return r[START:]
def stat(r, name):
    e = (1 + r).cumprod()
    cg = lambda x: (1 + x).prod() ** (252 / len(x)) - 1
    yr = (1 + r).groupby(r.index.year).prod() - 1
    a, b, c = r, r[:'2015-12-31'], r['2016-01-01':]
    row = dict(전략=name, 연수익=cg(a), 전반=cg(b), 후반=cg(c), MDD=(e / e.cummax() - 1).min(), Sharpe=a.mean() / a.std() * np.sqrt(252),
               최악연=yr.min(), 손실연수=int((yr < 0).sum()), 시장노출=float((r != 0).mean()))
    return row
me = C.resample('ME').last(); me.index = [C.index[C.index <= x][-1] for x in me.index]   # 월말 거래일
def monthly(wfun):
    return pd.DataFrame([wfun(me.iloc[:i + 1]) for i in range(len(me))], index=me.index).fillna(0)
mom = lambda m, k: m.iloc[-1] / m.iloc[-1 - k] - 1 if len(m) > k else m.iloc[-1] * np.nan
res = []
res.append(stat(ret['QQQ'][START:], 'QQQ 그냥 보유'))
res.append(stat(ret['SPY'][START:], 'SPY 그냥 보유'))
W = pd.DataFrame({'SPY': .6, 'IEF': .4}, index=me.index); res.append(stat(from_w(W), '60/40 (월 리밸런싱)'))
W = pd.DataFrame({'SPY': .3, 'TLT': .4, 'IEF': .15, 'GLD': .15}, index=me.index); res.append(stat(from_w(W), '올웨더(레이 달리오)'))
W = pd.DataFrame({'SPY': .25, 'TLT': .25, 'GLD': .25, 'SHY': .25}, index=me.index); res.append(stat(from_w(W), '영구 포트폴리오'))
# 추세추종
for a in ['QQQ', 'SPY']:
    on = (C[a] > C[a].rolling(200).mean())
    res.append(stat(from_w(pd.DataFrame({a: on.astype(float), 'SHY': (~on).astype(float)})), f'{a} 200일선 (아래면 단기채)'))
on = C['QQQ'].rolling(50).mean() > C['QQQ'].rolling(200).mean()
res.append(stat(from_w(pd.DataFrame({'QQQ': on.astype(float), 'SHY': (~on).astype(float)})), 'QQQ 골든크로스 50/200'))
m10 = me['QQQ'] > me['QQQ'].rolling(10).mean()
res.append(stat(from_w(pd.DataFrame({'QQQ': m10.astype(float), 'SHY': (~m10).astype(float)})), 'QQQ 10개월선 (메브 파버)'))
# 듀얼 모멘텀
def gem(us_):
    def f(m):
        a, b, c = mom(m[us_], 12), mom(m['EFA'], 12), mom(m['SHY'], 12)
        if np.isnan(a): return {}
        if a > c and a >= b: return {us_: 1}
        if b > c: return {'EFA': 1}
        return {'IEF': 1}
    return f
res.append(stat(from_w(monthly(gem('SPY'))), '듀얼 모멘텀 GEM (안토나치)'))
res.append(stat(from_w(monthly(gem('QQQ'))), '듀얼 모멘텀 (QQQ 버전)'))
def adm(m):
    sc = lambda a: (mom(m[a], 1) + mom(m[a], 3) + mom(m[a], 6)) / 3
    a, b = sc('QQQ'), sc('EFA')
    if np.isnan(a): return {}
    return {'QQQ': 1} if a >= b and a > 0 else {'EFA': 1} if b > 0 else {'TLT': 1}
res.append(stat(from_w(monthly(adm)), '가속 듀얼 모멘텀 (1·3·6개월)'))
A5 = ['SPY', 'EFA', 'IEF', 'VNQ', 'GLD']
def gtaa(m):
    if len(m) < 11: return {}
    return {a: .2 if m[a].iloc[-1] > m[a].iloc[-10:].mean() else 0 for a in A5} | {'SHY': .2 * sum(m[a].iloc[-1] <= m[a].iloc[-10:].mean() for a in A5)}
res.append(stat(from_w(monthly(gtaa)), 'GTAA5 (파버 자산배분)'))
SEC = ['XLB', 'XLE', 'XLF', 'XLI', 'XLK', 'XLP', 'XLU', 'XLV', 'XLY']
def sect(m):
    if len(m) < 13: return {}
    sc = pd.Series({a: (mom(m[a], 3) + mom(m[a], 6) + mom(m[a], 12)) / 3 for a in SEC}).nlargest(3)
    if m['SPY'].iloc[-1] < m['SPY'].iloc[-10:].mean(): return {'SHY': 1}
    return {a: 1 / 3 for a in sc.index}
res.append(stat(from_w(monthly(sect)), '섹터 모멘텀 상위 3 + 추세필터'))
def top1(m):
    U = ['QQQ', 'SPY', 'EFA', 'EEM', 'GLD', 'TLT', 'VNQ']
    if len(m) < 7: return {}
    sc = pd.Series({a: (mom(m[a], 1) + mom(m[a], 3) + mom(m[a], 6)) / 3 for a in U})
    return {sc.idxmax(): 1} if sc.max() > 0 else {'SHY': 1}
res.append(stat(from_w(monthly(top1)), '자산 7개 중 모멘텀 1등 갈아타기'))
# 단기 역추세·계절성 (QQQ)
def rsi(s, n):
    dlt = s.diff(); u = dlt.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(); dn = (-dlt.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + u / dn)
for a in ['QQQ', 'SPY']:
    c = C[a]; r2 = rsi(c, 2); up = c > c.rolling(200).mean(); ex = c > c.rolling(5).mean()
    pos = pd.Series(0.0, index=us); h = 0
    for i in range(len(us)):
        if h == 0 and up.iloc[i] and r2.iloc[i] < 10: h = 1
        elif h == 1 and ex.iloc[i]: h = 0
        pos.iloc[i] = h
    res.append(stat(from_w(pd.DataFrame({a: pos}), lag=0).shift(-0) if False else from_w(pd.DataFrame({a: pos})), f'{a} RSI(2) 눌림목 (래리 코너스)'))
c = C['QQQ']; r14 = rsi(c, 14); pos = pd.Series(0.0, index=us); h = 0
for i in range(len(us)):
    if h == 0 and r14.iloc[i] < 30: h = 1
    elif h == 1 and r14.iloc[i] > 70: h = 0
    pos.iloc[i] = h
res.append(stat(from_w(pd.DataFrame({'QQQ': pos})), 'QQQ RSI 30 매수 / 70 매도'))
mid = c.rolling(20).mean(); sd = c.rolling(20).std(); pos = pd.Series(0.0, index=us); h = 0
for i in range(len(us)):
    if h == 0 and c.iloc[i] < mid.iloc[i] - 2 * sd.iloc[i]: h = 1
    elif h == 1 and c.iloc[i] > mid.iloc[i]: h = 0
    pos.iloc[i] = h
res.append(stat(from_w(pd.DataFrame({'QQQ': pos})), 'QQQ 볼린저 하단 매수 / 중심선 매도'))
# 월말월초 효과: 마지막 거래일 종가 매수 → 다음 달 3번째 거래일 종가 매도
s = pd.Series(us, index=us); rank_end = s.groupby([us.year, us.month]).cumcount(ascending=False); rank_beg = s.groupby([us.year, us.month]).cumcount()
tom = ((rank_end == 0) | (rank_beg < 3)).astype(float)       # 보유하는 날(그 날 종가에 보유 상태)
res.append(stat(from_w(pd.DataFrame({'QQQ': tom}), lag=0) if False else ((tom.shift(1).fillna(0) * ret['QQQ']) - tom.diff().abs().fillna(0) * COST)[START:], 'QQQ 월말월초 효과 (4일만 보유)'))
# 변동성 돌파 (래리 윌리엄스, k=0.5): 시가 + 0.5×전일 변동폭 돌파 시 매수, 다음 날 시가 매도
for a in ['QQQ', 'SPY']:
    lvl = O[a] + 0.5 * (H[a] - L[a]).shift(1); hit = H[a] >= lvl
    buy = np.maximum(lvl, O[a]); r = (O[a].shift(-1) / buy - 1 - 2 * COST).where(hit, 0).fillna(0)
    res.append(stat(r[START:], f'{a} 변동성 돌파 k=0.5 (래리 윌리엄스)'))
    f_ = hit & (C[a].shift(1) > C[a].rolling(5).mean().shift(1))
    r = (O[a].shift(-1) / buy - 1 - 2 * COST).where(f_, 0).fillna(0)
    res.append(stat(r[START:], f'{a} 변동성 돌파 + 5일선 필터'))
T = pd.DataFrame(res).sort_values('Sharpe', ascending=False)
pd.set_option('display.width', 250)
f = T.copy()
for k in ['연수익', '전반', '후반', 'MDD', '최악연', '시장노출']: f[k] = f[k].map(lambda v: f"{v:+.1%}")
f['Sharpe'] = f['Sharpe'].round(2)
print(f.to_string(index=False)); T.to_csv('famous.csv', index=False)
