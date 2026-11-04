"""2라운드: 밤사이 미국 동종 3사(S&P500) · 외국인 보유율 변화 → 코스피 대형주 다음 날 (largecap_backtest.md 2라운드)
데이터 경로는 /tmp/btkr, /tmp/btdart, /tmp/bt-data-fr, /tmp/bt-data-us (각 bt-data-* 브랜치)"""
import sys, json, numpy as np, pandas as pd
sys.path.insert(0, "/home/claude/ji-hun-seong/surge-study/research"); sys.path.insert(0, "/home/claude/ji-hun-seong/surge-study")
import largecap_backtest as B
p, L, tr, te, rep, conds = B.main("/tmp/btkr/kospi_all.csv.gz", "/tmp/btdart/dart_filings.csv.gz")
# ── 외국인 보유율 변화 ──
fr = pd.read_csv("/tmp/bt-data-fr/kospi_foreign.csv.gz", dtype={"code": str}); fr["date"] = pd.to_datetime(fr["Date"].astype(str)); fr = fr.sort_values(["code", "date"])
fr["dfr1"] = fr.groupby("code")["FR"].diff(); fr["dfr5"] = fr.groupby("code")["FR"].diff(5)
p = p.merge(fr[["code", "date", "FR", "dfr1", "dfr5"]], on=["code", "date"], how="left")
# ── 미국: KR 날짜 d 에 대해 'd 이전 마지막 미국 거래일' 수익률 ──
us = pd.read_csv("/tmp/bt-data-us/us_prices.csv.gz", parse_dates=["Date"]); us = us.sort_values(["code", "Date"])
us["r"] = us.groupby("code")["Close"].pct_change() * 100
U = us.pivot(index="Date", columns="code", values="r")
U = U.loc[:, U.notna().mean() > 0.8]
krd = pd.DatetimeIndex(sorted(p["date"].unique()))
pos = U.index.searchsorted(krd, side="left") - 1                     # d 보다 앞선 마지막 미국 날짜
Ua = pd.DataFrame(U.values[np.clip(pos, 0, None)], index=krd, columns=U.columns); Ua[pos < 0] = np.nan
spx = Ua.mean(axis=1)                                                  # 미국 시장(동일가중) 밤사이
# KR 당일 수익률(전일 종가→당일 종가) = p.chg ; 대형주 후보 코드
p["chg_d"] = p["chg"]
LG = p[(p["tv20"] >= B.TV_MIN)]
codes = LG["code"].value_counts(); codes = codes[codes > 300].index
R = p[p["code"].isin(codes)].pivot(index="date", columns="code", values="chg_d")
TR = R.index < B.SPLIT
peers = {}
Utr = Ua[TR]; Utr_z = (Utr - Utr.mean()) / Utr.std()
for c in codes:
    y = R.loc[TR, c]; ok = y.notna()
    if ok.sum() < 300: continue
    yz = (y - y.mean()) / y.std()
    # 시장 영향 빼고(부분 상관) 미국 종목 중 가장 잘 맞는 3개
    Xz = Utr_z[ok]; cor = (Xz.mul(yz[ok], axis=0)).mean()
    top = cor.dropna().sort_values(ascending=False).head(3)
    peers[c] = list(top.index), list(top.round(3))
pk = pd.DataFrame({c: Ua[v[0]].mean(axis=1) for c, v in peers.items()})   # 상위 3개 평균 밤사이 수익률
peer_long = pk.stack().rename("us_peer").reset_index().rename(columns={"level_0": "date", "level_1": "code"})
p = p.merge(peer_long, on=["date", "code"], how="left")
p["us_mkt"] = p["date"].map(spx)
# 피처를 '전날 종가 시점' 행에 붙여 다음 날 수익을 예측하는 구조에 맞춤:
#   dfr1·dfr5: 오늘(t) 장 마감 → t+1 예측 (그대로)
#   us_peer·us_mkt: t+1 아침에 알 수 있음 → t 행에 '다음 날 아침 미국 신호'로 붙임
g = p.groupby("code")
p["us_peer_next"] = g["us_peer"].shift(-1); p["us_mkt_next"] = g["us_mkt"].shift(-1)
L2 = p[(p["tv20"] >= B.TV_MIN) & p["next"].notna() & p["rsi14"].notna() & (p["date"] >= "2015-01-01") & (p["next"].abs() < 35)].copy()
tr2, te2 = L2[L2["date"] < B.SPLIT], L2[L2["date"] >= B.SPLIT]
print("SDI peers:", peers.get("006400"), "| 삼성전자:", peers.get("005930"), "| 하이닉스:", peers.get("000660"))
conds2 = {
  "미국 동종 3사 밤사이 +3%↑": lambda d: d["us_peer_next"] >= 3, "미국 동종 +5%↑": lambda d: d["us_peer_next"] >= 5,
  "미국 동종 -3% 이하": lambda d: d["us_peer_next"] <= -3, "미국 시장 +1.5%↑": lambda d: d["us_mkt_next"] >= 1.5,
  "외국인 보유율 하루 +0.3%p↑": lambda d: d["dfr1"] >= 0.3, "외국인 5일 +1%p↑": lambda d: d["dfr5"] >= 1, "외국인 5일 -1%p 이하": lambda d: d["dfr5"] <= -1,
  "미국 동종 +3%↑ & 외국인 5일 순매수": lambda d: (d["us_peer_next"] >= 3) & (d["dfr5"] > 0),
}
for nm, D in (("학습", tr2), ("검증", te2)):
    print("\n==", nm, "기본 +5% 확률", round((D["next"] >= 5).mean() * 100, 2))
    print(pd.DataFrame([B.lift_table(D, k, fn(D).fillna(False)) for k, fn in conds2.items()]).to_string(index=False))
# 아침 신호 점수: 미국 동종 밤사이 수익률 자체로 순위
for nm, D in (("학습", tr2), ("검증", te2)):
    s = D["us_peer_next"].fillna(-99).values
    print("\n", nm, "아침 top10(미국 동종 상승순, +2%↑만):", B.topk(D, s, 10, 2))
    s2 = (D["us_peer_next"].fillna(-99) + 2 * (D["dfr5"].fillna(0) > 0.3)).values
    print(nm, "아침 top10(+외국인 5일 매수):", B.topk(D, s2, 10, 2))
json.dump({c: v for c, v in peers.items()}, open("/tmp/us_peers.json", "w"))
p[["date", "code", "us_peer_next", "dfr1", "dfr5", "next", "next_o2c", "tv20", "chg", "ret5"]].to_pickle("/tmp/p3.pkl")
