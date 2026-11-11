"""💱 환헤지(H) vs 환노출 백테스트 — S&P500 · 나스닥100

두 가지로 비교한다.
  ① 장기 이론 백테스트 (야후 지수 + 원/달러 + 한·미 3개월 금리)
     · 환노출(원화로 그냥 산 것)  = 지수 수익 × 원/달러 변화
     · 환헤지(H)                 = 지수 달러 수익 + (한국 3개월 금리 − 미국 3개월 금리) × 기간   ← 선물환을 굴리는 비용·이득
       금리: FRED(OECD) 3개월 은행간 금리 월별 IR3TIB01KRM156N · IR3TIB01USM156N. 못 받으면 금리차 0으로 두고 그렇게 표시
     · 가격 지수(배당 제외) · 보수·헤지 거래비용 제외 → 실제 ETF보다 조금 좋게 나옴
  ② 실제 국내 상장 ETF 쌍 (state/etf.db 의 KRX 일별 종가) — 보수·헤지 비용이 다 들어간 진짜 결과, 대신 기간이 짧음

사용:  python chartpage/fx_hedge.py      # 결과 요약 출력
"""
from __future__ import annotations

import io
import math
import re
import sys

IDX = {"sp": ("^GSPC", "S&P500", re.compile(r"S&P\s*500", re.I)),
       "nq": ("^NDX", "나스닥100", re.compile(r"나스닥\s*100|NASDAQ[\s-]*100", re.I))}
# 같은 지수라도 전략이 다른 ETF는 비교에서 뺌
NOT_PLAIN = re.compile(r"레버리지|인버스|2X|커버드|액티브|혼합|채권|버퍼|프리미엄|데일리|타겟|위클리|동일가중|성장|가치|배당|모멘텀|"
                       r"TOP|탑|금리|옵션|월배당|TR\b|엔비디아|테크", re.I)
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="


def _fred(sid):
    import pandas as pd
    import requests
    r = requests.get(FRED + sid, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    df.columns = ["d", "v"]
    df["d"] = pd.to_datetime(df["d"])
    df["v"] = pd.to_numeric(df["v"], errors="coerce")
    return df.dropna().set_index("d")["v"]


def _stats(s):
    """s: 1에서 시작하는 누적 지수(pd.Series, 날짜 인덱스)"""
    import numpy as np
    yrs = max((s.index[-1] - s.index[0]).days / 365.25, 1e-9)
    r = s.pct_change().dropna()
    return {"total": round((s.iloc[-1] / s.iloc[0] - 1) * 100, 1),
            "cagr": round(((s.iloc[-1] / s.iloc[0]) ** (1 / yrs) - 1) * 100, 2),
            "mdd": round(float((s / s.cummax() - 1).min() * 100), 1),
            "vol": round(float(r.std() * np.sqrt(252) * 100), 1)}


def _yearly(series: dict):
    """{이름: 누적지수} → [[연도, 이름별 수익률…]] (첫해·마지막 해는 부분 연도)"""
    import pandas as pd
    df = pd.DataFrame(series).dropna()
    ye = df.groupby(df.index.year).last()
    prev = pd.concat([df.iloc[[0]], ye.iloc[:-1]])
    prev.index = ye.index
    out = ((ye / prev.values - 1) * 100).round(1)
    return [[int(y), *[None if v != v else float(v) for v in row]] for y, row in zip(out.index, out.values)]


def _monthly(series: dict):
    import pandas as pd
    df = pd.DataFrame(series).dropna()
    m = df.groupby([df.index.year, df.index.month]).tail(1)
    return {"d": [d.strftime("%Y-%m") for d in m.index], **{k: [round(float(v), 4) for v in m[k]] for k in series}}


def long_run():
    import pandas as pd
    import data_sources as ds
    fx = ds._yahoo("KRW=X", "max")
    if fx is None:
        return {"error": "야후에서 원/달러(KRW=X)를 못 받았어요"}
    fx = fx["close"]
    fx = fx[(fx > 500) & (fx < 3000)]
    jump = fx.pct_change().abs()
    fx = fx[~((jump > 0.08) & (jump.shift(-1) > 0.08))]          # 하루만 튀었다 돌아오는 오류값 제거
    note = []
    try:
        kr, us = _fred("IR3TIB01KRM156N"), _fred("IR3TIB01USM156N")
        diff = (kr - us).dropna()
        rate_ok = True
    except Exception as e:
        diff, rate_ok = None, False
        note.append(f"금리 데이터(FRED) 못 받음 — 헤지 비용을 0으로 계산 ({type(e).__name__})")
    out = {"rate_ok": rate_ok, "note": note}
    for k, (sym, nm, _) in IDX.items():
        px = ds._yahoo(sym, "max")
        if px is None:
            out[k] = {"error": f"야후에서 {nm}({sym})를 못 받았어요"}
            continue
        df = pd.DataFrame({"p": px["close"]}).join(fx.rename("fx"), how="left")
        df["fx"] = df["fx"].ffill()
        df = df.dropna()
        if diff is not None:
            m = diff.reindex(pd.date_range(diff.index[0], df.index[-1], freq="D")).ffill()
            df["diff"] = m.reindex(df.index).ffill()
            df = df.dropna()
        else:
            df["diff"] = 0.0
        dt_y = df.index.to_series().diff().dt.days.fillna(0) / 365
        r_usd = df["p"].pct_change().fillna(0)
        usd = (1 + r_usd).cumprod()
        hed = (1 + r_usd + df["diff"].shift(1).fillna(df["diff"].iloc[0]) / 100 * dt_y).cumprod()
        unh = df["p"] * df["fx"] / (df["p"].iloc[0] * df["fx"].iloc[0])
        fxs = df["fx"] / df["fx"].iloc[0]
        S = {"unh": unh, "hed": hed, "usd": usd}
        yr = _yearly({**S, "fx": fxs})
        wins = sum(1 for y in yr if y[1] is not None and y[2] is not None and y[2] > y[1])
        out[k] = {"name": nm, "sym": sym, "from": df.index[0].strftime("%Y-%m-%d"), "to": df.index[-1].strftime("%Y-%m-%d"),
                  "fx0": round(float(df["fx"].iloc[0]), 1), "fx1": round(float(df["fx"].iloc[-1]), 1),
                  "diff_avg": round(float(df["diff"].mean()), 2), "diff_now": round(float(df["diff"].iloc[-1]), 2),
                  "stats": {n: _stats(s) for n, s in S.items()}, "yearly": yr, "hed_wins": wins, "years": len(yr),
                  "m": _monthly(S)}
    return out


def etf_pairs():
    """국내 상장 S&P500·나스닥100 ETF 중 환노출 1개·환헤지 1개(각각 순자산 최대)를 골라 같은 기간 비교"""
    import pandas as pd
    import etf as E
    c = E._conn()
    last = c.execute("SELECT MAX(d) FROM days WHERE n > 0").fetchone()[0]
    if not last:
        c.close()
        return {"error": "ETF 데이터가 아직 없어요"}
    cur = pd.read_sql("SELECT code, name, net, idx FROM px WHERE d=?", c, params=(last,))
    out = {}
    for k, (_, nm, rx) in IDX.items():
        m = cur[(cur["name"].str.contains(rx) | cur["idx"].fillna("").str.contains(rx)) & ~cur["name"].str.contains(NOT_PLAIN)]
        m = m[m["net"] >= E.MIN_NET]
        h = m[m["name"].str.contains(r"\(H\)")].sort_values("net", ascending=False)
        u = m[~m["name"].str.contains(r"\(H\)")].sort_values("net", ascending=False)
        if h.empty or u.empty:
            out[k] = {"error": f"{nm} 환헤지·환노출 쌍을 못 찾았어요"}
            continue
        hu, uu = h.iloc[0], u.iloc[0]
        px = pd.read_sql("SELECT d, code, close FROM px WHERE code IN (?, ?)", c, params=(hu["code"], uu["code"]))
        p = px.pivot(index="d", columns="code", values="close").dropna().sort_index()
        p.index = pd.to_datetime(p.index)
        if len(p) < 60:
            out[k] = {"error": "같이 거래된 기간이 너무 짧아요"}
            continue
        S = {"unh": p[uu["code"]] / p[uu["code"]].iloc[0], "hed": p[hu["code"]] / p[hu["code"]].iloc[0]}
        fees = dict(c.execute("SELECT code, fee FROM fee WHERE code IN (?, ?)", (hu["code"], uu["code"])).fetchall())
        out[k] = {"name": nm, "from": p.index[0].strftime("%Y-%m-%d"), "to": p.index[-1].strftime("%Y-%m-%d"),
                  "unh": {"code": uu["code"], "name": uu["name"], "net_eok": round(uu["net"] / 1e8), "fee": fees.get(uu["code"])},
                  "hed": {"code": hu["code"], "name": hu["name"], "net_eok": round(hu["net"] / 1e8), "fee": fees.get(hu["code"])},
                  "stats": {n: _stats(s) for n, s in S.items()}, "yearly": _yearly(S), "m": _monthly(S)}
    c.close()
    return out


def summary():
    out = {"kind": "fxh"}
    for key, fn in (("long", long_run), ("pairs", etf_pairs)):
        try:
            out[key] = fn()
        except Exception as e:
            out[key] = {"error": f"{type(e).__name__}: {str(e)[:160]}"}
    return out


if __name__ == "__main__":
    import json
    s = summary()
    for part in ("long", "pairs"):
        for k in ("sp", "nq"):
            v = (s.get(part) or {}).get(k) or s.get(part)
            if isinstance(v, dict) and "stats" in v:
                print(part, k, v["from"], "~", v["to"], json.dumps(v["stats"], ensure_ascii=False))
            else:
                print(part, k, v if not isinstance(v, dict) else v.get("error"))
    if len(sys.argv) > 1:
        print(json.dumps(s, ensure_ascii=False)[:2000])
