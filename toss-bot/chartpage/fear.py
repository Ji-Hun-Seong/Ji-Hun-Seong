"""😱 공포지수 — 지금 시장 심리 + '공포 때 사면 정말 더 벌까?' 백테스트 (QQQ·SPY)

지금 값
  · CNN 공포·탐욕 지수(0~100) — production.dataviz.cnn.io (막히면 생략)
  · VIX(변동성 지수) — 야후 ^VIX. 1990년부터 있어 긴 백테스트는 VIX로 함
    구간: 극도 공포 VIX 30↑ · 공포 20~30 · 보통 15~20 · 안심(탐욕) 15 미만

백테스트 (배당 재투자 수정주가 adjclose, 수수료·세금·환율 제외, 달러 기준)
  ① 공포 구간별 그 뒤 수익률 — 그날 샀다면 1·3·6·12개월 뒤 평균·중앙값·플러스 확률
  ② 매주 적립 전략 비교 (주 $100 기준)
     A 매주 금요일 $100                      — 기본 적립식
     B 공포 때 더 사기: 금요일 VIX 30↑ $300 · 20~30 $150 · 그 밖 $100   (돈이 더 들어감 → 연 수익률(IRR)로 비교)
     C 공포만 기다리기: 매주 $100을 현금으로 모아 두고, 금요일 VIX 25↑일 때만 모은 돈 전부 매수 (현금 이자 0)
     D 공포만 기다리기(CNN): C와 같되 신호를 CNN 지수 25 미만으로 — CNN 기록이 있는 기간만
  ③ 요일 비교 — 매주 월~금 중 어느 요일에 사도 결과가 비슷한지
  기간: 전체(QQQ 상장 1999-03~) · 최근 10년 · 최근 5년

사용:  python chartpage/fear.py      # 결과 요약 출력
"""
from __future__ import annotations

import math
import time

ASSETS = {"QQQ": "나스닥100 (QQQ)", "SPY": "S&P500 (SPY)"}
ZONES = [("xfear", "극도 공포", 30, 999), ("fear", "공포", 20, 30), ("mid", "보통", 15, 20), ("calm", "안심", 0, 15)]
CNN_BANDS = [("xfear", "극도 공포", 0, 25), ("fear", "공포", 25, 45), ("mid", "중립", 45, 55), ("greed", "탐욕", 55, 75), ("xgreed", "극도 탐욕", 75, 101)]
HORIZ = [("1m", 21), ("3m", 63), ("6m", 126), ("12m", 252)]
CNN_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata/"


# ── 데이터 ──────────────────────────────────────────
def _yahoo_adj(symbol: str):
    """야후 일봉 전체 → 수정주가(배당 재투자) Series"""
    import pandas as pd
    import requests
    from data_sources import UA
    r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
                     params={"range": "max", "interval": "1d", "events": "div,splits"}, headers=UA, timeout=20)
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    ind = res["indicators"]
    px = (ind.get("adjclose") or [{}])[0].get("adjclose") or ind["quote"][0]["close"]
    idx = pd.to_datetime(res["timestamp"], unit="s", utc=True).tz_convert("America/New_York").tz_localize(None).normalize()
    s = pd.Series(px, index=idx, dtype="float64").dropna()
    return s[~s.index.duplicated(keep="last")]


def _cnn():
    """CNN 공포·탐욕 → (지금 dict, 일별 Series 또는 None)"""
    import pandas as pd
    import requests
    from data_sources import UA
    h = {**UA, "Referer": "https://edition.cnn.com/", "Accept": "application/json"}
    js = None
    for start in ("2011-01-03", "2020-01-01", ""):
        try:
            r = requests.get(CNN_URL + start, headers=h, timeout=20)
            if r.status_code == 200:
                js = r.json()
                break
        except Exception:
            continue
    if not js:
        return None, None
    fg = js.get("fear_and_greed") or {}
    now = {"score": round(float(fg["score"]), 1) if fg.get("score") is not None else None, "rating": fg.get("rating"),
           "prev": {k: round(float(fg[k]), 1) for k in ("previous_close", "previous_1_week", "previous_1_month", "previous_1_year")
                    if fg.get(k) is not None}}
    pts = (js.get("fear_and_greed_historical") or {}).get("data") or []
    hist = None
    if pts:
        idx = pd.to_datetime([p["x"] for p in pts], unit="ms").normalize()
        hist = pd.Series([float(p["y"]) for p in pts], index=idx).sort_index()
        hist = hist[~hist.index.duplicated(keep="last")]
    return now, hist


# ── 계산 (데이터만 받으면 되는 순수 함수 — 테스트하기 쉽게) ─────────────────
def zone_of(v: float, table=ZONES):
    for k, _, lo, hi in table:
        if lo <= v < hi:
            return k
    return None


def _xirr(flows):
    """flows: [(날짜, 금액)] 투입은 −, 마지막 평가액은 + → 연 수익률(%)"""
    if not flows:
        return None
    t0 = flows[0][0]
    ts = [((d - t0).days / 365.25, a) for d, a in flows]

    def npv(r):
        return sum(a / (1 + r) ** t for t, a in ts)
    lo, hi = -0.99, 5.0
    flo, fhi = npv(lo), npv(hi)
    if flo * fhi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        fm = npv(mid)
        if abs(fm) < 1e-7:
            break
        if flo * fm < 0:
            hi, fhi = mid, fm
        else:
            lo, flo = mid, fm
    return round(mid * 100, 2)


def forward_table(px, sig, table=ZONES):
    """구간별: 그날 샀으면 n일 뒤 수익률 평균·중앙값·플러스 확률 (매일 겹치게 셈 — 표본이 서로 독립은 아님)"""
    import pandas as pd
    df = pd.DataFrame({"p": px, "z": sig.reindex(px.index).ffill()}).dropna()
    df["zone"] = df["z"].map(lambda v: zone_of(v, table))
    out = {"all": {"days": int(len(df))}}
    for k, *_ in table:
        out[k] = {"days": int((df["zone"] == k).sum())}
    for hk, n in HORIZ:
        fwd = df["p"].shift(-n) / df["p"] - 1
        for k in ["all"] + [t[0] for t in table]:
            f = (fwd if k == "all" else fwd[df["zone"] == k]).dropna()
            out[k][hk] = None if len(f) < 20 else {"avg": round(float(f.mean() * 100), 1), "med": round(float(f.median() * 100), 1),
                                                   "win": round(float((f > 0).mean() * 100)), "n": int(len(f))}
    out["share"] = {k: round(out[k]["days"] / max(out["all"]["days"], 1) * 100, 1) for k, *_ in table}
    return out


def _week_days(px, weekday):
    """주마다 그 요일(휴장이면 그 주의 가장 가까운 앞 거래일, 없으면 뒤) 거래일 목록"""
    import pandas as pd
    s = pd.Series(px.index, index=px.index)
    wk = s.index.to_period("W-SUN")
    days = []
    for _, g in s.groupby(wk):
        dd = list(g.index)
        on = [d for d in dd if d.weekday() == weekday]
        if on:
            days.append(on[0])
            continue
        before = [d for d in dd if d.weekday() < weekday]
        days.append(before[-1] if before else dd[0])
    return days


def run_dca(px, days, amount_fn, wait=False):
    """amount_fn(날짜) → (이번 주 적립금, 지금 살지 여부). wait=True면 안 살 때 현금으로 쌓음.
    반환: 투입·평가·수익률·IRR·평균 단가·매수 횟수·월별 곡선"""
    shares = cash = put = 0.0
    flows, buys = [], 0
    curve = {}
    for d in days:
        amt, go = amount_fn(d)
        put += amt
        flows.append((d, -amt))
        cash += amt
        if go or not wait:
            p = float(px.loc[d])
            shares += cash / p
            cash = 0.0
            buys += 1
        curve[d.strftime("%Y-%m")] = (round(shares * float(px.loc[d]) + cash, 2), round(put, 2))
    last_d = px.index[-1]
    val = shares * float(px.iloc[-1]) + cash
    flows.append((last_d, val))
    bought = put - cash
    return {"put": round(put), "value": round(val), "cash": round(cash), "ret": round((val / put - 1) * 100, 1) if put else None,
            "irr": _xirr(flows), "avg_cost_vs_last": round(bought / shares / float(px.iloc[-1]) * 100, 1) if shares else None,
            "buys": buys, "weeks": len(days), "curve": curve}


def strategies(px, vix, cnn=None, start=None, weekday=4):
    import pandas as pd
    p = px[px.index >= pd.Timestamp(start)] if start else px
    v = vix.reindex(p.index).ffill()
    days = [d for d in _week_days(p, weekday) if not math.isnan(v.loc[d])]
    out = {"from": p.index[0].strftime("%Y-%m-%d"), "to": p.index[-1].strftime("%Y-%m-%d"), "weeks": len(days)}
    out["A"] = run_dca(p, days, lambda d: (100.0, True))
    out["B"] = run_dca(p, days, lambda d: (300.0 if v.loc[d] >= 30 else 150.0 if v.loc[d] >= 20 else 100.0, True))
    out["C"] = run_dca(p, days, lambda d: (100.0, v.loc[d] >= 25), wait=True)
    if cnn is not None and len(cnn) > 250:
        c = cnn.reindex(p.index).ffill()
        cd = [d for d in days if d >= cnn.index[0] and not math.isnan(c.loc[d])]
        if len(cd) > 52:
            a2 = run_dca(p, cd, lambda d: (100.0, True))
            d2 = run_dca(p, cd, lambda d: (100.0, c.loc[d] < 25), wait=True)
            out["D"] = {**d2, "base": {k: a2[k] for k in ("put", "value", "ret", "irr", "avg_cost_vs_last")},
                        "from": cd[0].strftime("%Y-%m-%d")}
    # 월별 곡선은 A·B·C만, 차트용으로 정리
    ms = sorted(out["A"]["curve"])
    out["m"] = {"d": ms, **{k: [out[k]["curve"].get(m, (None, None))[0] for m in ms] for k in ("A", "B", "C")},
                "putA": [out["A"]["curve"][m][1] for m in ms], "putB": [out["B"]["curve"][m][1] for m in ms]}
    for k in ("A", "B", "C", "D"):
        if k in out:
            out[k].pop("curve", None)
    return out


def weekday_table(px, start=None):
    import pandas as pd
    p = px[px.index >= pd.Timestamp(start)] if start else px
    names = ["월", "화", "수", "목", "금"]
    rows = []
    for wd in range(5):
        r = run_dca(p, _week_days(p, wd), lambda d: (100.0, True))
        rows.append({"day": names[wd], "ret": r["ret"], "irr": r["irr"], "avg_cost_vs_last": r["avg_cost_vs_last"]})
    return rows


def compute(prices: dict, vix, cnn=None, today=None):
    import pandas as pd
    today = pd.Timestamp(today) if today is not None else max(s.index[-1] for s in prices.values())
    periods = [("all", "전체", None), ("10y", "최근 10년", today - pd.DateOffset(years=10)), ("5y", "최근 5년", today - pd.DateOffset(years=5))]
    out = {}
    for sym, px in prices.items():
        a = {"name": ASSETS.get(sym, sym), "fwd": forward_table(px, vix), "periods": {}}
        if cnn is not None and len(cnn) > 250:
            a["fwd_cnn"] = forward_table(px[px.index >= cnn.index[0]], cnn, CNN_BANDS)
            a["fwd_cnn"]["from"] = cnn.index[0].strftime("%Y-%m-%d")
        for pk, label, st in periods:
            r = strategies(px, vix, cnn, st)
            r["label"] = label
            r["weekday"] = weekday_table(px, st)
            a["periods"][pk] = r
        out[sym] = a
    return out


def summary():
    t0 = time.time()
    out = {"kind": "fear", "zones": [[k, n, lo, hi] for k, n, lo, hi in ZONES], "cnn_bands": [[k, n, lo, hi] for k, n, lo, hi in CNN_BANDS]}
    try:
        vix = _yahoo_adj("^VIX")
    except Exception as e:
        return {**out, "error": f"야후에서 VIX를 못 받았어요 ({type(e).__name__})"}
    vnow = float(vix.iloc[-1])
    out["vix"] = {"now": round(vnow, 2), "date": vix.index[-1].strftime("%Y-%m-%d"), "zone": zone_of(vnow),
                  "pct": round(float((vix < vnow).mean() * 100)),          # 1990년 이후 하루하루 중 지금보다 낮았던 날의 비율
                  "w1": round(float(vix.iloc[-6]), 2) if len(vix) > 6 else None,
                  "m1": round(float(vix.iloc[-22]), 2) if len(vix) > 22 else None,
                  "spark": [round(float(x), 1) for x in vix.iloc[-260:]], "spark_d": [d.strftime("%m-%d") for d in vix.index[-260:]]}
    cnn_hist = None
    try:
        cnow, cnn_hist = _cnn()
        if cnow:
            out["cnn"] = {**cnow, "zone": zone_of(cnow["score"], CNN_BANDS) if cnow.get("score") is not None else None,
                          "since": cnn_hist.index[0].strftime("%Y-%m-%d") if cnn_hist is not None else None}
    except Exception as e:
        out["cnn"] = {"error": f"{type(e).__name__}"}
    prices = {}
    for sym in ASSETS:
        try:
            prices[sym] = _yahoo_adj(sym)
        except Exception as e:
            out.setdefault("errors", {})[sym] = type(e).__name__
    if not prices:
        return {**out, "error": "야후에서 QQQ·SPY 가격을 못 받았어요"}
    start = max(s.index[0] for s in prices.values())               # 둘 다 있는 기간부터 (QQQ 1999-03)
    prices = {k: s[s.index >= start] for k, s in prices.items()}
    out["assets"] = compute(prices, vix, cnn_hist)
    out["took"] = round(time.time() - t0, 1)
    return out


if __name__ == "__main__":
    import json
    s = summary()
    print(json.dumps({k: s.get(k) for k in ("vix", "cnn", "error", "errors", "took")}, ensure_ascii=False, default=str)[:1500])
    for sym, a in (s.get("assets") or {}).items():
        for pk, r in a["periods"].items():
            print(sym, pk, r["from"], {k: {x: r[k][x] for x in ("put", "value", "ret", "irr", "buys")} for k in ("A", "B", "C") if k in r})
