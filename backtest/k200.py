"""
k200.py — 코스피200 전체(가치주 필터 없음)에서 BB+RSI 전략 변형 비교

    python backtest/k200.py [--telegram]

공통 매수: 종가 < 볼린저 하단(20,2σ) AND RSI(14) < 30 AND 종가 > 200일선. 다음 날 시가 체결.
변형
  A 기본      : 최대 5종목, 중심선/RSI55/10일/−8% 중 먼저
  B 10종목    : A와 같고 최대 10종목
  C 길게 보유  : 최대 5종목, RSI70/60일/−8% 중 먼저(중심선 청산 없음)
  D 10종목·길게: B+C
  +지수 파킹   : 쉬는 현금을 코스피200(ETF 가정)에 넣어 둠
비용: 매수 0.115%, 매도 0.315%(거래세 0.20% 포함). 지수 파킹의 ETF 매매비용은 무시.
주의: 오늘 기준 코스피200 구성종목을 과거에 적용 → 생존 편향으로 낙관적.
"""
from __future__ import annotations

import argparse
import json
import os
import time

import numpy as np
import pandas as pd
import requests

from backtest import OUT, fmt, indicators, kospi200_codes, prices, simulate, stats

VARIANTS = {
    "A 기본(5종목·10일)":         dict(max_pos=5),
    "B 10종목":                   dict(max_pos=10),
    "C 길게 보유(5종목·60일)":    dict(max_pos=5, hold_days=60, exit_rsi=70, mid_exit=False),
    "D 10종목·길게 보유":         dict(max_pos=10, hold_days=60, exit_rsi=70, mid_exit=False),
}


def yearly(eq: pd.Series) -> pd.Series:
    y = eq.resample("YE").last()
    return y.pct_change().fillna(y.iloc[0] / eq.iloc[0] - 1)


def main(telegram=False):
    k200 = kospi200_codes()
    data = {}
    for c in k200:
        try:
            data[c] = indicators(prices(c))
        except Exception as e:
            print("skip", c, e)
        time.sleep(0.15)
    idx = prices("KPI200")["Close"]
    idx_ret = idx.pct_change().fillna(0)
    print(f"코스피200 {len(k200)}개 중 시세 {len(data)}개")

    results, lines, curves = {}, [], {}
    for name, kw in VARIANTS.items():
        for park in (False, True):
            key = name + (" +지수 파킹" if park else "")
            eq, tr = simulate(data, True, idx_ret=idx_ret if park else None, **kw)
            s = stats(eq["equity"], tr, eq["npos"])
            results[key], curves[key] = s, eq["equity"]
            lines.append(f"• {key}\n  {fmt(s)}")
            print(key, fmt(s), flush=True)
            if not park and not tr.empty:
                tr.assign(name=tr["code"].map(k200)).to_csv(
                    os.path.join(OUT, f"k200_trades_{name.split()[0]}.csv"), index=False, encoding="utf-8-sig")
    start = next(iter(curves.values())).index[0]
    ix = idx[idx.index >= start]
    results["코스피200 지수"], curves["코스피200 지수"] = stats(ix), ix
    lines.append(f"• 코스피200 지수(단순보유)\n  {fmt(results['코스피200 지수'])}")

    os.makedirs(OUT, exist_ok=True)
    yt = pd.DataFrame({k: yearly(v) for k, v in curves.items()})
    yt.index = yt.index.year
    yt.to_csv(os.path.join(OUT, "k200_yearly.csv"), encoding="utf-8-sig", float_format="%.4f")

    period = f"{start.date()} ~ {ix.index[-1].date()}"
    text = (f"📊 코스피200 BB+RSI 백테스트 ({period})\n"
            f"매수: 볼린저 하단 이탈 + RSI<30 + 200일선 위 / 비용 반영\n\n"
            + "\n".join(lines)
            + "\n⚠️ 현재 구성종목 기준이라 생존 편향으로 낙관적")
    print(text)
    print(yt.map(lambda v: f"{v:+.1%}").to_string())
    with open(os.path.join(OUT, "k200_summary.txt"), "w", encoding="utf-8") as f:
        f.write(text + "\n\n연도별 수익률\n" + yt.map(lambda v: f"{v:+.1%}").to_string() + "\n")
    with open(os.path.join(OUT, "k200_summary.json"), "w", encoding="utf-8") as f:
        json.dump({"period": period, "results": {k: {kk: (None if isinstance(v, float) and np.isnan(v) else float(v))
                                                    for kk, v in s.items()} for k, s in results.items()}},
                  f, ensure_ascii=False, indent=2)

    if telegram:
        tok, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
        if tok and chat:
            r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                              data={"chat_id": chat, "text": text}, timeout=20)
            print("telegram", r.status_code)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--telegram", action="store_true")
    main(ap.parse_args().telegram)
