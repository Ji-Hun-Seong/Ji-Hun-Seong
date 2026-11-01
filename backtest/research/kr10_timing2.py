exec(open("kr10_park.py").read().split('print(f"{\'\':52s}')[0])
cash = assets["현금(연 2%)"]
for nm, useclose in [("다음 날 시가 진입·청산 (기존)", False), ("공시일 종가 진입·신호일 종가 청산 (상한)", True)]:
    g = dict(f); g["idx"] = cash; g["regime"] = pd.Series(True, index=dates)
    if useclose:
        g["O"] = C.shift(1)
    eq, ex, tr = simulate(g, entry=ev, score=rnd, max_pos=10, exit_sig=f["rsi14"] > 70, hold=10, park="smart")
    row(nm, eq)
