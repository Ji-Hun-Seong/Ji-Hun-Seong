exec(open("kr10.py").read().split('print(f"{\'\':40s}')[0])
cv = pickle.load(open("kr10_curves.pkl", "rb"))
ev = ev_matrix(["자사주취득", "자사주신탁"])
rnd = pd.DataFrame(np.random.default_rng(1).random(C.shape), index=dates, columns=C.columns)
sq = (f["bw_q"].rolling(5).min() < 0.2) & (C > f["up"]) & (f["rsi14"] > 60) & (f["ma50"] > f["ma200"]) & uni
def blend(curves, ws):
    df = pd.DataFrame(curves).loc[START:].ffill().pct_change().fillna(0)
    v = np.array(ws, float); out = []
    for i, d in enumerate(df.index):
        v = v * (1 + df.iloc[i].values); out.append(v.sum())
        if i + 1 < len(df.index) and df.index[i + 1].month != d.month:
            v = v.sum() * np.array(ws, float)
    return pd.Series(out, index=df.index)
print(f"{'':40s} | 전체 | IS | OOS | 연도")
P = {}
for mp in (5, 10, 15):
    for hold, xs in [(10, f["rsi14"] > 70), (20, f["rsi14"] > 70)]:
        for park in ("smart", True):
            eq, ex, tr = simulate(f, entry=ev, score=rnd, max_pos=mp, exit_sig=xs, hold=hold, park=park)
            P[(mp, hold, park)] = eq
            row(f"자사주 {mp}종목 {hold}일 + 쉬는돈 지수({'200일선 위만' if park == 'smart' else '항상'})", eq)
eqAp, _, _ = simulate(f, entry=sq, score=f["mom"], ascending=False, exit_sig=f["rsi14"] < 40, max_pos=15, hold=250, regime=True, park="smart")
row("스퀴즈 + 쉬는돈 지수(200일선 위만)", eqAp)
row("50/50: 자사주(10종목,10일,smart) + 스퀴즈(smart)", blend({"a": P[(10, 10, "smart")], "b": eqAp}, [.5, .5]))
row("50/50: 자사주(10종목,10일,smart) + 스퀴즈", blend({"a": P[(10, 10, "smart")], "b": cv["A"]}, [.5, .5]))
# 플라시보: 같은 빈도의 무작위 '공시' + 같은 파킹
freq = ev.loc[START:].values.mean(); out = []
for seed in range(10):
    rn = pd.DataFrame(np.random.default_rng(seed).random(C.shape) < freq, index=dates, columns=C.columns) & liq
    e2, _, _ = simulate(f, entry=rn, score=rnd, max_pos=10, exit_sig=f["rsi14"] > 70, hold=10, park="smart")
    out.append((m(e2)[0], m(e2, None, IS_END)[0], m(e2, IS_END + pd.Timedelta(days=1))[0]))
o = np.array(out); print(f"플라시보(무작위 진입+같은 파킹) 10회: 전체 {o[:,0].mean():+.1%} IS {o[:,1].mean():+.1%} OOS {o[:,2].mean():+.1%}")
pickle.dump(P, open("kr10b_curves.pkl", "wb"))
