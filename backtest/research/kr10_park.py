"""7차-2: 자사주 공시 스윙의 '쉬는 돈'을 코스피200 대신 다른 자산에 — 원화 기준"""
import sys, pickle
import numpy as np, pandas as pd
exec(open("kr10.py").read().split('print(f"{\'\':40s}')[0])
ev = ev_matrix(["자사주취득", "자사주신탁"])
rnd = pd.DataFrame(np.random.default_rng(1).random(C.shape), index=dates, columns=C.columns)
fx = E["KRW=X"].ffill()
def krw_us(t):                                     # 미국 종가는 한국 다음 거래일에 반영(하루 늦춤)
    s = (E[t] * fx).dropna()
    return s.reindex(s.index.union(dates)).ffill().shift(1).reindex(dates)
assets = {
 "현금(연 2%)": pd.Series(np.cumprod(np.full(len(dates), 1 + RF)), index=dates),
 "코스피200": idx.reindex(dates),
 "TIGER 나스닥100(133690, 원화)": E["133690.KS"].reindex(dates).ffill(),
 "나스닥100 QQQ×환율": krw_us("QQQ"),
 "S&P500 SPY×환율": krw_us("SPY"),
 "금 GLD×환율": krw_us("GLD"),
 "미국 장기국채 TLT×환율": krw_us("TLT"),
}
# 미국 나스닥 전략(목표변동성 45%, 200일선, 최대 2배; 합성 TQQQ+현금) 원화 환산
ex_us = open("beat_ndx_final.py").read().split("print(f\"\\n{'':40s}")[0]
ns = {}; exec(ex_us.replace('exec(open("beat_ndx_etf2.py")', 'exec(open("beat_ndx_etf2.py")'), ns)
us_eq = (1 + ns["x"]).cumprod()
s = (us_eq * fx.reindex(us_eq.index).ffill()).dropna()
assets["미국 나스닥 전략(6차)×환율"] = s.reindex(s.index.union(dates)).ffill().shift(1).reindex(dates)

print(f"{'':52s} | 전체(2015-11~) | IS 2015-11~2020 | OOS 2021~ | 연도별")
for name, a in assets.items():
    a = a.ffill()
    row(f"[자산만 보유] {name}", a / a.loc[START:].dropna().iloc[0])
print()
for name, a in assets.items():
    a = a.ffill().bfill()
    for smart in (False, True):
        if name.startswith(("현금", "미국 나스닥 전략")) and smart:
            continue
        g = dict(f); g["idx"] = a
        g["regime"] = (a > a.rolling(200).mean()) if smart else pd.Series(True, index=dates)
        eq, ex, tr = simulate(g, entry=ev, score=rnd, max_pos=10, exit_sig=f["rsi14"] > 70, hold=10, park="smart")
        row(f"자사주 + 파킹: {name}{' (200일선 위만)' if smart else ''}", eq)
