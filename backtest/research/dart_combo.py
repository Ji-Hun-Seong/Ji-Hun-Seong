exec(open("dart_strat.py").read().split("S = {")[0])
uni, _ = pickle.load(open("kr_pit.pkl", "rb"))
ev = ev_matrix(["자사주취득", "자사주신탁"])
rnd_score = pd.DataFrame(np.random.default_rng(1).random(C.shape), index=dates, columns=C.columns)
eqB, exB, trB = simulate(f, entry=ev, score=rnd_score, max_pos=10, exit_sig=never, hold=10)
show("공시: 자사주 10일", eqB, exB, trB)
eqB2, exB2, trB2 = simulate(f, entry=ev, score=rnd_score, max_pos=10, exit_sig=f["rsi14"] > 70, hold=10)
show("공시: 자사주 10일 + RSI>70 익절", eqB2, exB2, trB2)
eqBp, exBp, trBp = simulate(f, entry=ev, score=rnd_score, max_pos=10, exit_sig=never, hold=10, park=True)
show("공시: 자사주 10일 + 쉬는 돈 지수", eqBp, exBp, trBp)
sq = (f["bw_q"].rolling(5).min() < 0.2) & (C > f["up"]) & (f["rsi14"] > 60) & (f["ma50"] > f["ma200"]) & uni
eqA, exA, trA = simulate(f, entry=sq, score=f["mom"], ascending=False, exit_sig=f["rsi14"] < 40, max_pos=15, hold=250, regime=True)
show("스퀴즈 돌파", eqA, exA, trA)
ix = idx.reindex(eqA.index); ix = ix / ix.iloc[0]
r = pd.DataFrame({"A": eqA.pct_change(), "B": eqB.pct_change(), "I": ix.pct_change()}).fillna(0)
print("일간 수익률 상관:\n", r.corr().round(2).to_string())
def blend(ws):
    v = {k: w for k, w in ws.items()}; curve = []
    for i, d in enumerate(r.index):
        for k in v: v[k] *= 1 + r[k].iloc[i]
        curve.append(sum(v.values()))
        if i + 1 < len(r.index) and r.index[i + 1].month != d.month:
            tot = sum(v.values()); v = {k: tot * w for k, w in ws.items()}
    return pd.Series(curve, index=r.index)
for nm, ws in [("스퀴즈50+공시50", {"A": .5, "B": .5}), ("스퀴즈1/3+공시1/3+지수1/3", {"A": 1/3, "B": 1/3, "I": 1/3}),
               ("지수50+스퀴즈50(기존 추천)", {"A": .5, "I": .5}), ("지수50+공시50", {"B": .5, "I": .5})]:
    e = blend(ws); show(nm, e, pd.Series(1.0, index=e.index), None)
e = blend({"A": 1/3, "B": 1/3, "I": 1/3})
yr = pd.DataFrame({"3분할": e, "스퀴즈": eqA, "공시": eqB, "지수": ix}).resample("YE").last().pct_change(); yr.index = yr.index.year
print(yr.iloc[1:].map(lambda v: f"{v:+.0%}").T.to_string())
