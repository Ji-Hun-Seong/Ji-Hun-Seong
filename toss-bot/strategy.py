"""신호 계산 — 백테스트(backtest/research/fib_vol.py, 2015-11~2026-10, 시점별 거래대금 상위 200)와 같은 규칙

매수(종가 기준, 다음 날 시가 체결):
  ① 시장: KOSPI 종가 > 200일선
  ② 추세: 50일선 > 200일선
  ③ 볼린저 스퀴즈: 최근 SQ_DAYS일 안에 밴드폭이 1년 중 하위 SQ_Q
  ④ 볼린저 상단 돌파: 종가 > 20일 볼린저 상단(2σ)
  ⑤ 피보나치 100% 돌파: 종가 > 직전 FIB_N일 고점 (되돌림 구간을 다 회복하고 새 고점)
  ⑥ RSI14 > RSI_IN
  ⑦ 거래량: 오늘 거래량 ≥ 20일 평균 × VOL_X
  유니버스: 20일 평균 거래대금 상위 200 (상장 250일 이상)
  순위: 6개월 모멘텀 높은 순
매도: RSI14 < RSI_OUT (다음 날 시가)
  (피보나치 38.2%/61.8% 손절선, 고정 손절 -10%/-15%는 백테스트에서 수익을 줄여 기본값 끔. FIB_STOP=0.382 로 켤 수 있음)

백테스트 2015-11~2026-10 (비용 반영): 연 20.0%, MDD -40%, 평균 투자비중 53%  /  코스피200 연 13.9%, MDD -41%
  · 2015~2020 연 7.4% (지수 8.9%보다 낮음), 2021~2026 연 31.6% (지수 18.1%)
  · 주변 파라미터 18개 중앙값 연 14.7% → 실제 기대치는 '지수 비슷한 수익 + 절반의 투자비중'
  · 피보나치 되돌림(38~62%) 눌림목 매수는 108개 조합 모두 손실(중앙값 연 -2.8%)이라 쓰지 않음
"""
import numpy as np
import pandas as pd

P = dict(FIB_N=60, SQ_DAYS=10, SQ_Q=0.2, RSI_IN=60, RSI_OUT=40, VOL_X=1.0, TOP_TV=200, MAX_POS=10, FIB_STOP=None)


def rsi(c, n=14):
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def compute(panel, p=P):
    O, H, L, C, V = (panel[k].copy() for k in "ohlcv")
    idx = C.pop("^KOSPI") if "^KOSPI" in C else None
    for X in (O, H, L, V):
        X.drop(columns="^KOSPI", errors="ignore", inplace=True)
    if idx is not None and idx.notna().sum() > 0:
        days = idx.dropna().index                     # 지수가 있는 날 = 거래일 (이상한 날짜 봉 제거)
        idx = idx.loc[days]
        O, H, L, C, V = (X.reindex(days) for X in (O, H, L, C, V))
    mid, sd = C.rolling(20).mean(), C.rolling(20).std()
    up = mid + 2 * sd
    bw = 4 * sd / mid
    bw_q = bw.rolling(250, min_periods=120).rank(pct=True)
    r14 = rsi(C)
    ma50, ma200 = C.rolling(50).mean(), C.rolling(200).mean()
    mom = C.shift(5) / C.shift(126) - 1
    tv = (C * V).rolling(20).mean()
    age = C.notna().cumsum()
    tv_rank = tv.where(age > 250).rank(axis=1, ascending=False)
    uni = tv_rank <= p["TOP_TV"]
    prevhi = H.rolling(p["FIB_N"]).max().shift(1)
    lo_n = L.rolling(p["FIB_N"]).min().shift(1)
    vr = V / V.rolling(20).mean()
    regime = (idx > idx.rolling(200).mean()) if idx is not None else pd.Series(True, index=C.index)
    entry = ((bw_q.rolling(p["SQ_DAYS"]).min() < p["SQ_Q"]) & (C > up) & (C > prevhi) & (r14 > p["RSI_IN"])
             & (vr >= p["VOL_X"]) & (ma50 > ma200) & uni)
    return dict(C=C, O=O, entry=entry, rsi=r14, mom=mom, regime=regime, up=up, prevhi=prevhi, lo_n=lo_n, vr=vr,
                bw_q=bw_q, tv=tv, idx=idx)


def today_signals(f, positions, p=P):
    """마지막 날짜 기준 신호. positions: {sym: {...,'stop': 손절가}}"""
    d = f["C"].index[-1]
    regime = bool(f["regime"].iloc[-1]) if len(f["regime"]) else False
    sells = []
    for s, pos in positions.items():
        if s not in f["C"].columns:
            continue
        r, c = f["rsi"].at[d, s], f["C"].at[d, s]
        if pd.notna(r) and r < p["RSI_OUT"]:
            sells.append((s, f"RSI {r:.0f} < {p['RSI_OUT']}"))
        elif pos.get("stop") and pd.notna(c) and c < pos["stop"]:
            sells.append((s, f"피보나치 손절선 {pos['stop']:,.0f} 이탈"))
    buys = []
    if regime:
        e = f["entry"].loc[d]
        cand = [s for s in e[e.fillna(False)].index if s not in positions]
        cand.sort(key=lambda s: -(f["mom"].at[d, s] if pd.notna(f["mom"].at[d, s]) else -9))
        for s in cand:
            hi, lo = f["prevhi"].at[d, s], f["lo_n"].at[d, s]
            buys.append({"symbol": s, "close": float(f["C"].at[d, s]), "rsi": float(f["rsi"].at[d, s]),
                         "vr": float(f["vr"].at[d, s]), "mom": float(f["mom"].at[d, s]),
                         "fib_hi": float(hi), "fib_lo": float(lo),
                         "stop": float(hi - (hi - lo) * p["FIB_STOP"]) if p["FIB_STOP"] and pd.notna(lo) else None})
    return {"date": str(d.date()), "regime": regime, "idx": float(f["idx"].iloc[-1]) if f["idx"] is not None else None,
            "idx_ma200": float(f["idx"].rolling(200).mean().iloc[-1]) if f["idx"] is not None else None,
            "sells": sells, "buys": buys}
