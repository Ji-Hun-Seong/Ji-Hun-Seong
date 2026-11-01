"""6차-4: 최종안 점검 — 목표변동성 45%, 200일선, 20일 변동성, 최대 2배, TQQQ+현금 주간 리밸런싱"""
import sys
import numpy as np, pandas as pd
exec(open("beat_ndx_etf2.py").read().split("print(f\"\\n{'':40s}")[0])
v = r.rolling(20).std() * np.sqrt(252)
L = (0.45 / v).clip(upper=2) * (ndx > ndx.rolling(200).mean())
x, w = run_w(L)
print(f"\n{'':40s} | " + " | ".join(PER))
show("나스닥100 보유", r); show("최종안 (합성 TQQQ)", x); show("고정 1.6배 보유(평균 레버리지와 같음)", lev(1.6))
# 실제 TQQQ 가격으로 (2010~)
tq_real = E["TQQQ"].reindex(days).pct_change()
tq_bak = tq.copy(); tq = tq_real.fillna(tq_bak)
x2, w2 = run_w(L); tq = tq_bak
s = "2010-03-01"
for name, y in [("나스닥100", r), ("최종안 합성", x), ("최종안 실제 TQQQ", x2)]:
    c, m = perf(y, s, None); print(f"2010-03~ {name}: 연 {c:+.1%}, MDD {m:+.0%}")
yr = pd.DataFrame({"나스닥100": (1 + r).resample("YE").prod() - 1, "최종안": (1 + x).resample("YE").prod() - 1,
                   "평균레버리지": (w * 3).resample("YE").mean()}).loc["2000":]
yr.index = yr.index.year
print(yr.T.map(lambda z: f"{z:+.0%}" if abs(z) < 5 else f"{z:.1f}").to_string())
ch = (w.diff().abs() > 0.01).loc["2015-11-01":]
print(f"리밸런싱 횟수: 연 {ch.sum() / 11:.0f}회, 현금(0배) 기간 비율 {(w.loc['2015-11-01':] < 0.01).mean():.0%}, 평균 레버리지 {(w * 3).loc['2015-11-01':].mean():.2f}배")
print("최근 상태:", ndx.index[-1].date(), f"NDX {ndx.iloc[-1]:,.0f} / 200일선 {ndx.rolling(200).mean().iloc[-1]:,.0f}, 20일 변동성 {v.iloc[-1]:.1%}, 목표 레버리지 {L.iloc[-1]:.2f}배 → TQQQ 비중 {L.iloc[-1] / 3:.0%}")
