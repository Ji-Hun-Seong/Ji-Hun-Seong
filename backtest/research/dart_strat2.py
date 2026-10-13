exec(open("dart_strat.py").read().split("S = {")[0])
ev = ev_matrix(["자사주취득", "자사주신탁"])
rnd_score = pd.DataFrame(np.random.default_rng(1).random(C.shape), index=dates, columns=C.columns)
V = {}
for reg in (False, True):
    for hold in (10, 20, 40):
        for mp in (10, 20):
            eq, ex, tr = simulate(f, entry=ev, score=rnd_score, max_pos=mp, exit_sig=never, hold=hold, regime=reg)
            V[(reg, hold, mp)] = show(f"자사주 hold{hold} pos{mp} regime={reg}", eq, ex, tr)
for nm, extra in [("%b<0.5", f["pb"] < 0.5), ("RSI<60", f["rsi14"] < 60), ("200일선 아래", ~up), ("거래대금<30억", f["tv"] < 3e9)]:
    eq, ex, tr = simulate(f, entry=ev & extra, score=rnd_score, max_pos=10, exit_sig=never, hold=20, regime=True)
    show(f"자사주 + {nm} hold20 regime", eq, ex, tr)
eq, ex, tr = simulate(f, entry=ev, score=rnd_score, max_pos=10, exit_sig=f["rsi14"] > 70, hold=20, regime=True)
show("자사주 hold20 regime + RSI>70 익절", eq, ex, tr)
eq, ex, tr = simulate(f, entry=ev, score=rnd_score, max_pos=10, exit_sig=never, hold=20, regime=True, stop=0.10)
show("자사주 hold20 regime + 손절10%", eq, ex, tr)
