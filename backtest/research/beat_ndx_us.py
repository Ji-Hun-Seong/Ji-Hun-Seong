"""6차: 나스닥100(QQQ) 이기기 — 미국 S&P500 시점별 구성 종목 모멘텀 (월간 리밸런싱)"""
import sys, itertools
import numpy as np, pandas as pd
D = sys.argv[1] if len(sys.argv) > 1 else "/tmp/bt"
d = pd.read_csv(f"{D}/us_prices.csv.gz", parse_dates=["Date"])
C = d.pivot(index="Date", columns="code", values="Close").sort_index()
spy = C.pop("SPY")
hist = pd.read_csv(f"{D}/us_hist.csv", parse_dates=["date"]).sort_values("date")
rows = []
for dd, t in zip(hist["date"], hist["tickers"]):
    s = {x.strip().replace(".", "-") for x in t.split(",")}
    rows.append(pd.Series(C.columns.isin(list(s)), index=C.columns, name=dd))
mem = pd.DataFrame(rows); mem = mem[~mem.index.duplicated(keep="last")].reindex(C.index, method="ffill").fillna(False).astype(bool)
e = pd.read_csv(f"{D}/etf_prices.csv.gz", parse_dates=["Date"])
E = e.pivot(index="Date", columns="code", values="Close").sort_index()
START, IS_END = pd.Timestamp("2015-11-01"), pd.Timestamp("2020-12-31")
COST = 0.0015

def stats(r, name, w=None):
    r = r[r.index >= START]
    def m(x):
        eq = (1 + x).cumprod(); yrs = len(x) / 12
        return eq.iloc[-1] ** (1 / yrs) - 1, (eq / eq.cummax() - 1).min(), x.mean() / x.std() * np.sqrt(12)
    a, i, o = m(r), m(r[r.index <= IS_END]), m(r[r.index > IS_END])
    print(f"{name:42s} | {a[0]:+.1%} MDD{a[1]:+.1%} Sh{a[2]:.2f} | IS {i[0]:+.1%} | OOS {o[0]:+.1%} MDD{o[1]:+.1%}", flush=True)
    return a[0], i[0], o[0], a[1]

ME = C.resample("ME").last()
mret = ME.pct_change(fill_method=None)
qqq = E["QQQ"].resample("ME").last().pct_change()
QQ = stats(qqq, "벤치마크 QQQ (나스닥100)")
stats(E["SPY"].resample("ME").last().pct_change(), "SPY")
memM = mem.resample("ME").last()
spyM = spy.resample("ME").last(); spy10 = spyM > spyM.rolling(10).mean()
bil = E["BIL"].resample("ME").last().pct_change().fillna(0) if "BIL" in E else 0

def momentum(lb=12, skip=1, top=10, filt=False, vol_adj=False, hi52=False):
    sig = ME.shift(skip) / ME.shift(lb) - 1
    if vol_adj:
        dv = C.pct_change(fill_method=None).rolling(126).std().resample("ME").last()
        sig = sig / dv
    if hi52:
        sig = ME / C.rolling(252).max().resample("ME").last()
    sig = sig.where(memM)
    out, prev = [], set()
    for i in range(len(ME) - 1):
        t, t1 = ME.index[i], ME.index[i + 1]
        if filt and not spy10.iloc[i]:
            r = bil.get(t1, 0) if hasattr(bil, "get") else 0
            out.append((t1, r - (COST if prev else 0))); prev = set(); continue
        pick = sig.loc[t].dropna().nlargest(top).index
        r = mret.loc[t1, pick].fillna(-0.5 if False else 0).mean()
        turn = len(set(pick) - prev) / top
        out.append((t1, r - 2 * COST * turn)); prev = set(pick)
    return pd.Series(dict(out))

print("\n[S&P500 시점별 구성 · 모멘텀 상위 N · 월간]")
res = []
for lb, top, filt, va in itertools.product([3, 6, 12], [5, 10, 20, 30], [False, True], [False, True]):
    a = stats(momentum(lb, 1, top, filt, va), f"모멘텀 {lb}개월 상위{top}{' 추세필터' if filt else ''}{' 변동성조정' if va else ''}")
    res.append((lb, top, filt, va) + a)
g = pd.DataFrame(res, columns="lb top filt va CAGR IS OOS MDD".split())
print(f"\n{len(g)}개 중 QQQ 초과: 전체 {(g.CAGR > QQ[0]).mean():.0%}, IS {(g.IS > QQ[1]).mean():.0%}, OOS {(g.OOS > QQ[2]).mean():.0%}, 둘 다 {((g.IS > QQ[1]) & (g.OOS > QQ[2])).mean():.0%}")
for top in [5, 10, 20]:
    stats(momentum(12, 1, top, hi52=True), f"52주 고점 근접 상위{top}")
g.to_csv("beat_ndx_us_grid.csv", index=False)
