"""largecap_backtest.py — 대형주(평소 거래대금 300억↑) '다음 날 +5%↑' 예측 백테스트 (코스피 2015~2026)

질문: 삼성SDI 같은 대형주는 지금 급등 후보 규칙(중소형 기준)에서 거의 안 뽑힌다. 대형주만 따로 뽑으면 맞힐 수 있나?

데이터: bt-data-kr 브랜치 kospi_all.csv.gz(수정주가 일봉), bt-data-dart 브랜치 dart_filings.csv.gz(공시)
방법:
  1) 날마다 대형주(20일 평균 거래대금 ≥ 300억)만 남기고, 장 마감 때 알 수 있는 특징만으로 다음 날 수익률을 본다
  2) 특징별 '다음 날 +5%↑ 확률'(기본 확률 대비 몇 배인지) — 2015~2021(학습)으로 규칙을 정하고
  3) 2022~2026(검증, 규칙을 만들 때 안 본 기간)에서 매일 상위 10개를 골랐을 때 성적을 대형주 전체 평균과 비교
     비교 대상: 현재 v1 규칙(candidates.score_row)을 대형주에 그대로 쓴 경우

  python surge-study/research/largecap_backtest.py /tmp/btkr/kospi_all.csv.gz /tmp/btdart/dart_filings.csv.gz
"""
from __future__ import annotations

import json
import os
import re
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
TV_MIN = 300e8
SPLIT = "2022-01-01"

CATS = [("공급계약", r"단일판매|공급계약"), ("자사주", r"자기주식취득|주식소각|신탁계약체결"), ("실적", r"영업\(잠정\)|잠정실적|매출액또는손익구조"),
        ("무상증자", r"무상증자"), ("투자", r"신규시설투자|유형자산양수|타법인주식"), ("증자CB", r"유상증자|전환사채|신주인수권|교환사채"),
        ("합병", r"합병|공개매수|최대주주변경")]


def load(prices_path, filings_path):
    p = pd.read_csv(prices_path, dtype={"code": str}, parse_dates=["Date"])
    p = p.rename(columns=str.lower).sort_values(["code", "date"])
    p = p[(p["close"] > 0) & (p["volume"] >= 0)]
    g = p.groupby("code", group_keys=False)
    c, v = p["close"], p["volume"]
    p["tv"] = c * v
    p["chg"] = g["close"].pct_change() * 100
    p["tv20"] = g["tv"].transform(lambda s: s.rolling(20).mean().shift(1))         # 오늘 제외 평소 거래대금
    p["vol_ratio"] = v / g["volume"].transform(lambda s: s.rolling(20).mean().shift(1))
    p["ret5"] = g["close"].pct_change(5)
    p["ret20"] = g["close"].pct_change(20)
    ma20 = g["close"].transform(lambda s: s.rolling(20).mean())
    sd20 = g["close"].transform(lambda s: s.rolling(20).std(ddof=0))
    up, lo = ma20 + 2 * sd20, ma20 - 2 * sd20
    p["pctb"] = (c - lo) / (up - lo)
    bw = (up - lo) / ma20
    p["bw_pctile"] = bw.groupby(p["code"]).transform(lambda s: s.rolling(120).rank(pct=True))
    hi250 = g["high"].transform(lambda s: s.rolling(250, min_periods=60).max())
    p["from_high"] = c / hi250 - 1
    d = g["close"].diff()
    gain = d.clip(lower=0).groupby(p["code"]).transform(lambda s: s.ewm(alpha=1 / 14, adjust=False).mean())
    loss = (-d.clip(upper=0)).groupby(p["code"]).transform(lambda s: s.ewm(alpha=1 / 14, adjust=False).mean())
    p["rsi14"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    rng = (p["high"] - p["low"]).replace(0, np.nan)
    p["close_pos"] = ((c - p["low"]) / rng).fillna(1.0)
    p["upper_wick"] = (p["high"] - np.maximum(p["open"], c)) / g["close"].shift(1) * 100
    ma5, ma60, ma120 = (g["close"].transform(lambda s, n=n: s.rolling(n).mean()) for n in (5, 60, 120))
    p["ma_aligned"] = (ma5 > ma20) & (ma20 > ma60) & (ma60 > ma120)
    p["up_days"] = g["chg"].transform(lambda s: (s > 0).astype(int).groupby((s <= 0).cumsum()).cumsum())
    p["next"] = g["close"].shift(-1) / c * 100 - 100                                  # 다음 날 종가 수익률
    p["next_o2c"] = g["close"].shift(-1) / g["open"].shift(-1) * 100 - 100             # 다음 날 시가 매수 → 종가
    p["next3"] = g["close"].shift(-3) / c * 100 - 100

    f = pd.read_csv(filings_path, dtype=str)
    f["nm"] = f["report_nm"].str.replace(r"\s", "", regex=True)
    f["date"] = pd.to_datetime(f["rcept_dt"])
    for tag, pat in CATS:
        f[tag] = f["nm"].str.contains(pat)
    fl = f.groupby(["code", "date"])[[t for t, _ in CATS]].any().reset_index()
    p = p.merge(fl, on=["code", "date"], how="left")
    for t, _ in CATS:
        p[t] = p[t].fillna(False).astype(bool)
    p["dart_ok"] = p["code"].isin(set(f["code"]))
    return p


def lift_table(L, cond_name, mask):
    s = L[mask]
    base = (L["next"] >= 5).mean()
    return {"조건": cond_name, "건수": int(len(s)), "다음날+5%확률": round((s["next"] >= 5).mean() * 100, 2),
            "기본대비": round((s["next"] >= 5).mean() / base, 2) if base else None,
            "다음날평균": round(s["next"].mean(), 2), "다음날시가→종가": round(s["next_o2c"].mean(), 2), "3일평균": round(s["next3"].mean(), 2)}


def v1_score(L):
    import candidates as C
    out = []
    cols = ["chg", "vol_ratio", "tv", "close_pos", "upper_wick", "bw_pctile", "pctb", "from_high", "ma_aligned", "rsi14", "ret5", "ret20", "up_days", "tv20"]
    titles = {t: [{"title": nm}] for t, nm in [("공급계약", "단일판매공급계약체결"), ("자사주", "자기주식취득결정"), ("실적", "영업(잠정)실적"),
                                              ("무상증자", "무상증자결정"), ("투자", "신규시설투자등"), ("증자CB", "유상증자결정"), ("합병", "합병결정")]}
    for r in L[cols + [t for t, _ in CATS]].itertuples(index=False):
        rd = r._asdict()
        f = {k: (None if pd.isna(rd[k]) else rd[k]) for k in ("bw_pctile", "pctb", "from_high", "rsi14", "ret5", "ret20")}
        f.update({"ma_aligned": bool(rd["ma_aligned"]), "up_days": int(rd["up_days"] or 0), "tv20_avg": rd["tv20"]})
        tb = {"chg": rd["chg"], "vol_ratio": rd["vol_ratio"], "tv": rd["tv"], "close_pos": rd["close_pos"], "upper_wick": rd["upper_wick"]}
        fl = [x for t, _ in CATS if rd[t] for x in titles[t]]
        out.append(C.score_row(f, tb, fl)[0])
    return np.array(out)


def large_score(L, rules):
    """학습 기간에서 고른 규칙(rules)의 가중합"""
    s = np.zeros(len(L))
    for name, fn, w in rules:
        s += w * fn(L).astype(float)
    return s


def topk(L, score, k=10, min_score=None):
    d = L.assign(score=score)
    if min_score is not None:
        d = d[d["score"] >= min_score]
    d = d.sort_values(["date", "score", "tv"], ascending=[True, False, False])
    top = d.groupby("date").head(k)
    daily = top.groupby("date").agg(avg=("next", "mean"), o2c=("next_o2c", "mean"), n=("next", "size"), hit5=("next", lambda x: (x >= 5).mean()))
    mkt = L.groupby("date")["next"].mean()
    daily["mkt"] = mkt.reindex(daily.index)
    return {"days": int(len(daily)), "picks": int(daily["n"].sum()), "avg_next": round(top["next"].mean(), 3), "avg_o2c": round(top["next_o2c"].mean(), 3),
            "avg_3d": round(top["next3"].mean(), 3), "hit5": round((top["next"] >= 5).mean() * 100, 2), "lose3": round((top["next"] <= -3).mean() * 100, 2),
            "market_avg": round(L["next"].mean(), 3), "excess_vs_mkt": round((daily["avg"] - daily["mkt"]).mean(), 3),
            "win_days": round((daily["avg"] > daily["mkt"]).mean() * 100, 1)}


def main(pp, fp):
    p = load(pp, fp)
    L = p[(p["tv20"] >= TV_MIN) & p["next"].notna() & p["rsi14"].notna() & (p["date"] >= "2015-01-01")].copy()
    L = L[L["next"].abs() < 35]                                      # 이상치(거래정지 후 재개 등) 제외
    tr, te = L[L["date"] < SPLIT], L[L["date"] >= SPLIT]
    rep = {"universe": f"코스피 대형주(20일 평균 거래대금 ≥ {TV_MIN / 1e8:.0f}억)", "rows_train": len(tr), "rows_test": len(te),
           "stocks_per_day": round(L.groupby("date").size().mean(), 1),
           "base_hit5_train": round((tr["next"] >= 5).mean() * 100, 2), "base_hit5_test": round((te["next"] >= 5).mean() * 100, 2)}

    conds = {
        "오늘 공급계약 공시": lambda d: d["공급계약"], "오늘 자사주 공시": lambda d: d["자사주"], "오늘 잠정실적 공시": lambda d: d["실적"],
        "오늘 투자·지분취득 공시": lambda d: d["투자"], "오늘 증자·CB 공시": lambda d: d["증자CB"], "오늘 합병·공개매수": lambda d: d["합병"],
        "거래량 2배↑ & 오늘 0~5%": lambda d: (d["vol_ratio"] >= 2) & d["chg"].between(0, 5),
        "거래량 2배↑ & 오늘 -3% 이하": lambda d: (d["vol_ratio"] >= 2) & (d["chg"] <= -3),
        "거래량 3배↑": lambda d: d["vol_ratio"] >= 3,
        "오늘 +5%↑": lambda d: d["chg"] >= 5, "오늘 +8%↑": lambda d: d["chg"] >= 8,
        "오늘 -5% 이하(급락)": lambda d: d["chg"] <= -5, "오늘 -8% 이하": lambda d: d["chg"] <= -8,
        "5일 +15%↑": lambda d: d["ret5"] >= 0.15, "5일 -15% 이하": lambda d: d["ret5"] <= -0.15,
        "RSI 30 이하": lambda d: d["rsi14"] <= 30, "RSI 70 이상": lambda d: d["rsi14"] >= 70,
        "볼린저 스퀴즈(하위 15%)": lambda d: d["bw_pctile"] <= 0.15, "볼린저 하단 이탈(%b<0)": lambda d: d["pctb"] < 0,
        "볼린저 상단 돌파(%b>1)": lambda d: d["pctb"] > 1, "52주 고점 -3% 이내": lambda d: d["from_high"] >= -0.03,
        "52주 고점 대비 -40% 이하": lambda d: d["from_high"] <= -0.4, "고가 마감(종가 위치 0.9↑) & 상승": lambda d: (d["close_pos"] >= 0.9) & (d["chg"] > 0),
        "정배열": lambda d: d["ma_aligned"],
    }
    rep["lift_train"] = [lift_table(tr, k, fn(tr)) for k, fn in conds.items()]
    rep["lift_test"] = [lift_table(te, k, fn(te)) for k, fn in conds.items()]
    return p, L, tr, te, rep, conds


if __name__ == "__main__":
    p, L, tr, te, rep, conds = main(sys.argv[1], sys.argv[2])
    print(json.dumps({k: v for k, v in rep.items() if not k.startswith("lift")}, ensure_ascii=False, indent=1))
    for k in ("lift_train", "lift_test"):
        print("\n==", k)
        print(pd.DataFrame(rep[k]).to_string(index=False))
