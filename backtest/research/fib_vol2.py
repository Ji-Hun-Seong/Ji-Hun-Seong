"""5차-2: 돌파 전략의 청산 규칙 비교 (피보 손절선, 고정 손절) + 거래량 1.5배 + 최종안 연도별"""
import sys
import numpy as np, pandas as pd
sys.path.insert(0, ".")
exec(open("fib_vol.py").read().split('print("\\n[대표 설정]")')[0])
r, hi, lo, a = FIB[60]
prevhi = H.rolling(60).max().shift(1); prevlo = L.rolling(60).min().shift(1)
base = (f["bw_q"].rolling(10).min() < 0.2) & (C > prevhi) & (C > f["up"]) & (f["rsi14"] > 60) & (f["ma50"] > f["ma200"]) & uni
def run(name, vmin, extra_exit=None, stop=None):
    e = base & (vr >= vmin)
    x = f["rsi14"] < 40
    if extra_exit is not None:
        x = x | extra_exit
    kw = dict(entry=e, score=f["mom"], ascending=False, exit_sig=x, max_pos=10, hold=250, regime=True, stop=stop)
    eq, ex, tr = simulate(f, **kw); line(name, split_metrics(eq, ex, tr)); return eq
# 피보 손절선: 진입일의 (직전60일 고점 - 0.382*(고점-저점)) 을 진입 이후 고정 → 근사: 신호일 값을 ffill (종목별 진입 시점 근사)
stopline = (prevhi - (prevhi - prevlo) * 0.382).where(base).ffill(limit=120)
eq0 = run("최종 후보: 거래량1.5배, RSI<40 청산", 1.5)
run("거래량 2배", 2.0); run("거래량 조건 없음", 0)
run("+ 피보 38.2% 손절선", 1.5, extra_exit=C < stopline)
run("+ 피보 61.8% 손절선", 1.5, extra_exit=C < (prevhi - (prevhi - prevlo) * 0.618).where(base).ffill(limit=120))
run("+ 고정 손절 -10%", 1.5, stop=0.10)
run("+ 고정 손절 -15%", 1.5, stop=0.15)
yr = pd.DataFrame({"전략": eq0.resample("YE").last().pct_change(), "코스피200": idx.loc[START:].resample("YE").last().pct_change()})
yr.index = yr.index.year
print(yr.iloc[1:].map(lambda x: f"{x:+.0%}").T.to_string())
