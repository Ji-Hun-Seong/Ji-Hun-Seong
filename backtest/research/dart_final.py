exec(open("dart_combo.py").read().split('eqB, exB, trB')[0])
B = {}
for nm, ex_sig in [("RSI>70", f["rsi14"] > 70), ("BB상단 or RSI>70", (C > f["up"]) | (f["rsi14"] > 70)), ("RSI>65", f["rsi14"] > 65), ("RSI>75", f["rsi14"] > 75)]:
    for hold in (10, 15):
        eq, ex, tr = simulate(f, entry=ev, score=rnd_score, max_pos=10, exit_sig=ex_sig, hold=hold)
        B[(nm, hold)] = eq; show(f"자사주 {hold}일 / 익절 {nm}", eq, ex, tr)
# 다른 순위(무작위 대신 RSI 낮은 순)로도 견고한지
eq, ex, tr = simulate(f, entry=ev, score=f["rsi14"], ascending=True, max_pos=10, exit_sig=f["rsi14"] > 70, hold=10)
show("자사주 10일 / RSI>70, 순위=RSI 낮은순", eq, ex, tr)
neg = ev_matrix(["유상증자", "전환사채", "교환사채", "BW", "자사주처분"]).astype(float).rolling(20, min_periods=1).max().astype(bool)
sq = (f["bw_q"].rolling(5).min() < 0.2) & (C > f["up"]) & (f["rsi14"] > 60) & (f["ma50"] > f["ma200"]) & uni
eqA, exA, trA = simulate(f, entry=sq, score=f["mom"], ascending=False, exit_sig=f["rsi14"] < 40, max_pos=15, hold=250, regime=True)
show("스퀴즈", eqA, exA, trA)
eqA2, exA2, trA2 = simulate(f, entry=sq & ~neg, score=f["mom"], ascending=False, exit_sig=f["rsi14"] < 40, max_pos=15, hold=250, regime=True)
show("스퀴즈 - 최근20일 악재공시 제외", eqA2, exA2, trA2)
eqB = B[("RSI>70", 10)]
ix = idx.reindex(eqA.index); ix = ix / ix.iloc[0]
r = pd.DataFrame({"A": eqA.pct_change(), "B": eqB.pct_change(), "I": ix.pct_change()}).fillna(0)
def blend(ws):
    v = dict(ws); curve = []
    for i, d in enumerate(r.index):
        for k in v: v[k] *= 1 + r[k].iloc[i]
        curve.append(sum(v.values()))
        if i + 1 < len(r.index) and r.index[i + 1].month != d.month:
            tot = sum(v.values()); v = {k: tot * w for k, w in ws.items()}
    return pd.Series(curve, index=r.index)
for nm, ws in [("최종: 스퀴즈50+자사주공시50", {"A": .5, "B": .5}), ("스퀴즈1/3+공시1/3+지수1/3", {"A": 1/3, "B": 1/3, "I": 1/3})]:
    e = blend(ws); show(nm, e, pd.Series(1.0, index=e.index), None)
e = blend({"A": .5, "B": .5})
yr = pd.DataFrame({"최종50/50": e, "스퀴즈": eqA, "자사주공시": eqB, "코스피200": ix}).resample("YE").last().pct_change(); yr.index = yr.index.year
print(yr.iloc[1:].map(lambda v: f"{v:+.0%}").T.to_string())
