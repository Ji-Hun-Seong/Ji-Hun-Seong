"""6차-2: 나스닥100 이기기 — 나스닥 레버리지 + 추세/변동성 규칙 (일간, 다음 날 적용)
합성 레버리지: L×NDX 일수익 − (L−1)×단기금리 − 보수(연 0.95%) → 1986년부터 닷컴·금융위기 포함 검증
"""
import sys, itertools
import numpy as np, pandas as pd
D = sys.argv[1] if len(sys.argv) > 1 else "/tmp/bt"
e = pd.read_csv(f"{D}/etf_prices.csv.gz", parse_dates=["Date"])
E = e.pivot(index="Date", columns="code", values="Close").sort_index()
ndx = E["^NDX"].dropna()
days = ndx.index
rf = (E["^IRX"].reindex(days).ffill() / 100 / 252).fillna(0)       # 일간 단기금리
r = ndx.pct_change().fillna(0)
COST = 0.001        # 포지션 변경 시 편도 비용

def lev(L, fee=0.0095):
    return L * r - (L - 1) * rf - fee / 252

# 합성 검증: 실제 QLD/TQQQ와 비교
for L, t in [(2, "QLD"), (3, "TQQQ")]:
    real = E[t].dropna(); s = real.index[0]
    syn = (1 + lev(L)[r.index > s]).cumprod(); rr = real / real.iloc[0]
    print(f"합성 {L}x vs {t}: 실제 {rr.iloc[-1]:.1f}배, 합성 {syn.iloc[-1]:.1f}배 ({s.date()}~)")

PER = {"10년(2015-11~)": ("2015-11-01", None), "IS 2015-11~2020": ("2015-11-01", "2020-12-31"), "OOS 2021~": ("2021-01-01", None),
       "장기 1990~": ("1990-01-01", None), "닷컴 2000~2002": ("2000-01-01", "2002-12-31"), "금융위기 2007~2009": ("2007-06-01", "2009-12-31")}

def perf(x, a, b):
    x = x[(x.index >= a) & ((x.index <= b) if b else True)]
    eq = (1 + x).cumprod(); yrs = len(x) / 252
    return eq.iloc[-1] ** (1 / yrs) - 1, (eq / eq.cummax() - 1).min()

def show(name, x):
    cells = []
    for k, (a, b) in PER.items():
        c, m = perf(x, a, b); cells.append(f"{c:+.1%}/{m:+.0%}")
    print(f"{name:40s} | " + " | ".join(cells), flush=True)
    return {k: perf(x, a, b)[0] for k, (a, b) in PER.items()}

def run(sig_pos):
    """sig_pos: 각 날 종가 기준 목표 레버리지(0=현금) → 다음 날 적용"""
    pos = sig_pos.shift(1).fillna(0)
    ret = pos.clip(lower=0) * r - (pos - 1).clip(lower=0) * rf + (1 - pos).clip(lower=0) * rf - (pos > 1) * 0.0095 / 252 * pos / pos.where(pos > 0, 1)
    ret -= pos.diff().abs().fillna(0) * COST
    return ret

print(f"\n{'':40s} | " + " | ".join(f"{k}(연/MDD)" for k in PER))
B = show("나스닥100 보유", r)
show("나스닥100 2배 보유 (QLD 합성)", lev(2))
show("나스닥100 3배 보유 (TQQQ 합성)", lev(3))

ma = {n: ndx.rolling(n).mean() for n in (50, 100, 150, 200, 250)}
vol = r.rolling(20).std() * np.sqrt(252)
res = []
print("\n[추세 필터: 지수가 N일선 위면 L배, 아래면 현금]")
for n, L in itertools.product((50, 100, 150, 200, 250), (1, 2, 3)):
    p = (ndx > ma[n]).astype(float) * L
    out = show(f"{n}일선 위 {L}배", run(p)); res.append(("trend", n, L, None) + tuple(out.values()))
print("\n[추세 필터 + 버퍼(위 2% 돌파 시 진입, 아래 2% 이탈 시 청산)]")
for n, L in itertools.product((100, 200), (2, 3)):
    up, dn = ndx > ma[n] * 1.02, ndx < ma[n] * 0.98
    st = pd.Series(np.nan, index=days); st[up] = 1; st[dn] = 0; p = st.ffill().fillna(0) * L
    out = show(f"{n}일선±2% {L}배", run(p)); res.append(("buffer", n, L, None) + tuple(out.values()))
print("\n[변동성 목표: 레버리지 = 목표변동성/최근20일 변동성 (최대 3배), 200일선 아래면 현금 옵션]")
for tv, f in itertools.product((0.2, 0.25, 0.3, 0.4), (False, True)):
    p = (tv / vol).clip(upper=3)
    if f:
        p = p * (ndx > ma[200])
    out = show(f"목표변동성 {tv:.0%}{' +200일선' if f else ''}", run(p)); res.append(("voltgt", 200 if f else 0, tv, None) + tuple(out.values()))
g = pd.DataFrame(res, columns=["kind", "n", "L", "x"] + list(PER))
for k in PER:
    g[k + ">"] = g[k] > B[k]
print("\n나스닥100 보유보다 높은 비율:", {k: f"{g[k + '>'].mean():.0%}" for k in PER})
ok = g[g["IS 2015-11~2020>"] & g["OOS 2021~>"] & g["장기 1990~>"]]
print("IS·OOS·장기 모두 이긴 규칙:"); print(ok[["kind", "n", "L"] + list(PER)].round(3).to_string())
g.to_csv("beat_ndx_etf_grid.csv", index=False)
