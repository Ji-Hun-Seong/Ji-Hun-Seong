"""
squeeze.py — 최종 후보: 볼린저 스퀴즈 돌파 + RSI 청산 + 시장 추세 필터 (코스피200)

규칙(일봉, 종가 신호 → 다음 날 시가 체결)
  시장 필터 : 코스피200 지수 > 200일선일 때만 신규 매수
  종목 추세 : 50일선 > 200일선
  스퀴즈    : 최근 5일 중 하루라도 볼린저 대역폭(20,2σ)이 1년 중 하위 20%
  돌파      : 종가 > 볼린저 상단 AND RSI(14) > 60
  우선순위  : 6개월 모멘텀(최근 1주 제외) 높은 순, 최대 15종목 동일비중
  청산      : RSI(14) < 40
  비용      : 매수 0.115%, 매도 0.315%(거래세 0.20% 포함)

    git fetch origin bt-data && git show origin/bt-data:k200_prices.csv.gz > backtest/data/k200_prices.csv.gz
    python backtest/squeeze.py
"""
import numpy as np
import pandas as pd

from engine import START, IS_END, features, load, simulate, split_metrics

P = dict(sq_q=0.2, sq_win=5, rsi_in=60, rsi_out=40, max_pos=15)


def strategy(f, sq_q, sq_win, rsi_in, rsi_out, max_pos):
    C = f["C"]
    squeeze = f["bw_q"].rolling(sq_win).min() < sq_q
    entry = squeeze & (C > f["up"]) & (f["rsi14"] > rsi_in) & (f["ma50"] > f["ma200"])
    return dict(entry=entry, score=f["mom"], ascending=False, exit_sig=f["rsi14"] < rsi_out,
                max_pos=max_pos, hold=250, regime=True)


if __name__ == "__main__":
    piv, idx = load()
    f = features(piv, idx)
    eq, ex, tr = simulate(f, **strategy(f, **P))
    bench = idx[idx.index >= START]
    m, bm = split_metrics(eq, ex, tr), split_metrics(bench, pd.Series(1.0, index=bench.index))
    for k, label in [("ALL", "전체"), ("IS", f"~{IS_END.year}"), ("OOS", f"{IS_END.year + 1}~")]:
        s, b = m[k], bm[k]
        print(f"{label:6s} 전략 CAGR {s['CAGR']:+.1%} MDD {s['MDD']:+.1%} Sharpe {s['Sharpe']:.2f} 노출 {s['Expo']:.0%}"
              f"  | 지수 CAGR {b['CAGR']:+.1%} MDD {b['MDD']:+.1%} Sharpe {b['Sharpe']:.2f}")
    a = m["ALL"]
    print(f"거래 {a['N']}회, 승률 {a['Win']:.0%}, 건당 평균 {a['AvgTr']:+.1%}, 평균 보유 {a['Days']:.0f}거래일")
