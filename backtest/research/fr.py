"""외국인 수급(보유율 변화) 신호 검증 — 코스피, 시점별 거래대금 상위 200 유니버스."""
import sys, pickle
import numpy as np, pandas as pd
sys.path.insert(0, ".")
from engine import *

piv, idx = load("/tmp/claude-0/btkr/kospi_all.csv.gz", "KPI200")
keep = [c for c in piv["Close"].columns if c.endswith("0")]
piv = {k: v[keep] for k, v in piv.items()}
f = features(piv, idx); C = f["C"]
uni, _ = pickle.load(open("kr_pit.pkl", "rb"))
fr = pd.read_csv("/tmp/claude-0/btfr/kospi_foreign.csv.gz", dtype={"code": str, "Date": str})
fr["Date"] = pd.to_datetime(fr["Date"])
FR = fr.pivot(index="Date", columns="code", values="FR").reindex(index=C.index, columns=C.columns)
FR = FR.where(FR > 0).ffill(limit=3).shift(1)         # 공표 시차를 고려해 하루 늦게 사용
for k in (5, 20, 60):
    f[f"dfr{k}"] = FR - FR.shift(k)
    f[f"dfr{k}_r"] = f[f"dfr{k}"].where(uni).rank(axis=1, pct=True)
print("외국인 보유율 커버리지(유니버스 내):", float((FR.notna() & uni).loc[START:].sum().sum() / uni.loc[START:].sum().sum()))

def show(name, m, extra=""):
    print(f"{name:40s} | " + " | ".join(f"{k} {m[k]['CAGR']:+.1%} MDD {m[k]['MDD']:+.1%} Sh {m[k]['Sharpe']:.2f}" for k in m) + extra, flush=True)

# ---------- T1: 외국인 순매수 강도 5분위별 이후 수익률 ----------
print("\n[T1] 외국인 순매수(보유율 변화) 5분위별 이후 수익률 — 유니버스 내 평균 대비 초과")
for k in (5, 20, 60):
    q = pd.cut(f[f"dfr{k}_r"].stack(), [0, .2, .4, .6, .8, 1.0], labels=[1, 2, 3, 4, 5]).unstack()
    for h in (5, 20, 60):
        fwd = C.shift(-h) / C - 1
        ex = fwd.sub(fwd.where(uni).mean(axis=1), axis=0)
        out = []
        for nm, a, b in [("IS", START, IS_END), ("OOS", IS_END, pd.Timestamp("2026-12-31"))]:
            vals = [ex.loc[a:b].where(q.loc[a:b] == i).stack().mean() for i in (1, 2, 3, 4, 5)]
            out.append(f"{nm} " + " ".join(f"{v:+.2%}" for v in vals))
        print(f"  {k}일 순매수 → {h}일 후  (1=외국인 매도 최다 … 5=매수 최다): " + " || ".join(out))

bench = idx.loc[START:]
show("코스피200 보유", split_metrics(bench, pd.Series(1.0, index=bench.index)))
up = C > f["ma200"]; sq = f["bw_q"].rolling(5).min() < 0.2
base_sq = sq & (C > f["up"]) & (f["rsi14"] > 60) & (f["ma50"] > f["ma200"]) & uni
def run(name, entry, exit_sig, score=None, asc=False, mp=15, hold=250, regime=True):
    eq, ex, tr = simulate(f, entry=entry, score=f["mom"] if score is None else score, ascending=asc,
                          exit_sig=exit_sig, max_pos=mp, hold=hold, regime=regime)
    m = split_metrics(eq, ex, tr)
    show(name, m, f" | N{m['ALL'].get('N',0)} 승률 {m['ALL'].get('Win',0):.0%} 건당 {m['ALL'].get('AvgTr',0):+.1%} 노출 {m['ALL']['Expo']:.0%}")
    return eq, m

print("\n[T2] 전략")
run("기존: 가격 스퀴즈", base_sq, f["rsi14"] < 40)
run("스퀴즈 + 외국인 20일 순매수(>0)", base_sq & (f["dfr20"] > 0), f["rsi14"] < 40)
run("스퀴즈 + 외국인 20일 순매수 상위40%", base_sq & (f["dfr20_r"] > 0.6), f["rsi14"] < 40)
run("스퀴즈, 순위=외국인 순매수", base_sq, f["rsi14"] < 40, score=f["dfr20_r"])
run("스퀴즈 + 외국인 매도 전환 시 청산", base_sq, (f["rsi14"] < 40) | ((f["dfr20"] < 0) & (f["rsi14"] < 50)))
pull = up & (f["pb"] < 0.2) & (f["rsi14"] < 40) & uni
run("눌림(%b<0.2,RSI<40) 단독", pull, (f["rsi14"] > 70) | (f["pb"] > 1), score=f["rsi14"], asc=True, hold=40)
run("외국인 매집 중 눌림 (상위20%)", pull & (f["dfr20_r"] > 0.8), (f["rsi14"] > 70) | (f["pb"] > 1), score=f["dfr20_r"], hold=40)
run("외국인 매집 중 눌림 (60일 상위20%)", pull & (f["dfr60_r"] > 0.8), (f["rsi14"] > 70) | (f["pb"] > 1), score=f["dfr60_r"], hold=40)
# 순수 외국인 추종(월 1회 리밸런싱 근사: 순위 이탈 시 매도)
top = f["dfr20_r"] > 0.9
run("외국인 순매수 상위10% 추종", top & up, f["dfr20_r"] < 0.5, score=f["dfr20_r"], hold=60)

# ---------- T3: 시장 수준 외국인 수급으로 지수 타이밍 ----------
w_tv = f["tv"].where(uni)
agg = (f["dfr20"] * w_tv).sum(axis=1) / w_tv.where(f["dfr20"].notna()).sum(axis=1)   # 거래대금 가중 평균 보유율 변화
r = idx.pct_change()
fwd20 = idx.shift(-20) / idx - 1
print("\n[T3] 시장 전체 외국인 20일 순매수(가중) 5분위 → 코스피200 20일 후")
for nm, a, b in [("IS", START, IS_END), ("OOS", IS_END, None)]:
    qq = pd.qcut(agg.loc[a:b].dropna(), 5, labels=False)
    print(f"  {nm}: " + " ".join(f"Q{i+1} {fwd20.loc[a:b][qq == i].mean():+.2%}" for i in range(5)))
def timing(w):
    w = w.shift(1).fillna(0)
    ret = w * r + (1 - w) * 0.02 / 252 - w.diff().abs().fillna(0) * 0.0005
    return (1 + ret.loc[START:].fillna(0)).cumprod(), w.loc[START:]
ma200 = idx.rolling(200).mean()
mid = idx.rolling(20).mean(); sdv = idx.rolling(20).std(); pbi = (idx - (mid - 2 * sdv)) / (4 * sdv); ri = rsi(idx, 14)
for nm, w in [("200일선 추세", (idx > ma200).astype(float)),
              ("외국인 순매수>0 일 때만 보유", (agg > 0).astype(float)),
              ("추세 OR 외국인 순매수", ((idx > ma200) | (agg > 0)).astype(float)),
              ("추세 AND 외국인 순매수", ((idx > ma200) & (agg > 0)).astype(float))]:
    eq, ww = timing(w); show(f"[지수] {nm}", split_metrics(eq, ww), f" | 평균비중 {ww.mean():.2f}")
pickle.dump((FR, agg), open("fr.pkl", "wb"))
