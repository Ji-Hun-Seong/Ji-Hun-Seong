"""11차: 현금 들고 있다가 패닉셀에 사기 (QQQ, 레버리지 없음). 현금은 미국 단기국채 금리(^IRX). 신호 다음 날 종가 체결, 비용 0.1%."""
import numpy as np, pandas as pd
d = pd.read_csv('/tmp/etf/etf_prices.csv.gz', parse_dates=['Date']); C = d.pivot(index='Date', columns='code', values='Close')
q = C['QQQ'].dropna(); ix = q.index; vix = C['^VIX'].reindex(ix).ffill(); cash_r = (C['^IRX'].reindex(ix).ffill() / 100 / 252).fillna(0)
r = q.pct_change().fillna(0); dd = q / q.cummax() - 1; COST = 0.001
def run(w, start):
    w = w.shift(1).fillna(0)
    x = (w * r + (1 - w) * cash_r - w.diff().abs().fillna(0) * COST)[start:]
    e = (1 + x).cumprod(); yr = (1 + x).groupby(x.index.year).prod() - 1
    return dict(연수익=(e.iloc[-1]) ** (252 / len(x)) - 1, MDD=(e / e.cummax() - 1).min(), Sharpe=x.mean() / x.std() * np.sqrt(252),
                최악연=yr.min(), 주식보유비율=w[start:].mean(), 매수횟수=int((w.diff() > 0.01)[start:].sum()))
def state(buy, sell):
    w = pd.Series(0.0, index=ix); h = 0
    for i in range(len(ix)):
        if h == 0 and buy.iloc[i]: h = 1
        elif h == 1 and sell.iloc[i]: h = 0
        w.iloc[i] = h
    return w
newhigh = dd >= -0.001
S = {'QQQ 그냥 보유': pd.Series(1.0, index=ix), '현금만 보유': pd.Series(0.0, index=ix)}
for x in [.1, .2, .3, .4]:
    S[f'고점 대비 -{x:.0%}에 매수 → 전고점 회복 시 매도'] = state(dd <= -x, newhigh)
    S[f'고점 대비 -{x:.0%}에 매수 → 1년 뒤 매도'] = None
for v in [30, 40]:
    S[f'VIX {v} 넘으면 매수 → VIX 20 아래 매도'] = state(vix > v, vix < 20)
    S[f'VIX {v} 넘으면 매수 → 전고점 회복 시 매도'] = state(vix > v, newhigh)
rs = 100 - 100 / (1 + r.clip(lower=0).ewm(alpha=1/14, adjust=False).mean() / (-r.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean())
S['RSI 30 아래 매수 → 전고점 회복 시 매도'] = state(rs < 30, newhigh)
# 섞기: 기본 비중 + 패닉 때 현금 투입(전고점 회복하면 기본 비중으로)
for base in [.5, .7]:
    t = pd.Series(base, index=ix); lvl = 0; out = []
    for i in range(len(ix)):
        k = 3 if dd.iloc[i] <= -.3 else 2 if dd.iloc[i] <= -.2 else 1 if dd.iloc[i] <= -.1 else 0
        lvl = 0 if newhigh.iloc[i] else max(lvl, k)
        out.append(base + (1 - base) * lvl / 3)
    S[f'QQQ {base:.0%} 기본 + 하락 -10/-20/-30%마다 현금 투입'] = pd.Series(out, index=ix)
    S[f'QQQ {base:.0%} + 현금 {1-base:.0%} 고정'] = pd.Series(base, index=ix)
# 1년 뒤 매도 변형
for x in [.1, .2, .3, .4]:
    w = pd.Series(0.0, index=ix); h = 0
    for i in range(len(ix)):
        if h == 0 and dd.iloc[i] <= -x: h = 252
        w.iloc[i] = 1.0 if h > 0 else 0.0; h = max(0, h - 1)
    S[f'고점 대비 -{x:.0%}에 매수 → 1년 뒤 매도'] = w
for start in ['1999-03-10', '2010-01-04']:
    T = pd.DataFrame({k: run(w, start) for k, w in S.items()}).T.sort_values('연수익', ascending=False)
    for c in ['연수익', 'MDD', '최악연', '주식보유비율']: T[c] = T[c].map(lambda v: f"{v:+.1%}")
    T['Sharpe'] = T['Sharpe'].astype(float).round(2); print('\n=====', start, '~ 2026-10'); print(T.to_string()); T.to_csv(f'panic_{start[:4]}.csv')
print('\n고점 대비 -20% 이하였던 날 비율', f"{(dd <= -.2).mean():.0%}", '| -30% 이하', f"{(dd['2010':] <= -.3).mean():.1%}(2010~)")
