exec(open("fr.py").read().split("# ---------- T1")[0])
bench = idx.loc[START:]
up = C > f["ma200"]; sq = f["bw_q"].rolling(5).min() < 0.2
base_sq = sq & (C > f["up"]) & (f["rsi14"] > 60) & (f["ma50"] > f["ma200"]) & uni
# T1 유의성: 월말 표본(겹치지 않는 60일은 3개월 간격)으로 상위20% - 유니버스 평균
fwd = C.shift(-60) / C - 1; ex = fwd.sub(fwd.where(uni).mean(axis=1), axis=0)
me = [d for d in C.index[C.index >= START] if d.month % 3 == 0 and (d + pd.Timedelta(days=1)).month != d.month or False]
me = C.loc[START:].resample("QE").last().index
me = [C.index[C.index <= d][-1] for d in me]
for nm, a, b in [("IS", START, IS_END), ("OOS", IS_END, pd.Timestamp("2026-07-01"))]:
    xs = []
    for d in me:
        if a <= d <= b:
            m = (f["dfr60_r"].loc[d] > 0.8)
            xs.append(ex.loc[d][m].mean())
    xs = pd.Series(xs).dropna()
    print(f"[유의성] 60일 외국인 순매수 상위20% → 60일 초과수익 {nm}: 분기 평균 {xs.mean():+.2%}, 플러스 분기 {(xs>0).mean():.0%}, n={len(xs)}, t={xs.mean()/xs.std()*np.sqrt(len(xs)):.2f}")
def run(name, entry, exit_sig, score=None, asc=False, mp=15, hold=250, regime=True):
    eq, exn, tr = simulate(f, entry=entry, score=f["mom"] if score is None else score, ascending=asc, exit_sig=exit_sig, max_pos=mp, hold=hold, regime=regime)
    m = split_metrics(eq, exn, tr)
    print(f"{name:36s} | " + " | ".join(f"{k} {m[k]['CAGR']:+.1%} MDD {m[k]['MDD']:+.1%} Sh {m[k]['Sharpe']:.2f}" for k in m) + f" | N{m['ALL'].get('N',0)}", flush=True)
run("기존 스퀴즈", base_sq, f["rsi14"] < 40)
run("스퀴즈, 순위=60일 외국인 매집", base_sq, f["rsi14"] < 40, score=f["dfr60_r"])
run("스퀴즈 + 60일 외국인 매집 상위50%", base_sq & (f["dfr60_r"] > 0.5), f["rsi14"] < 40)
run("스퀴즈 + 60일 외국인 매도 하위20% 제외", base_sq & (f["dfr60_r"] > 0.2), f["rsi14"] < 40)
run("60일 매집 상위20% & 상승추세 (60일 보유)", (f["dfr60_r"] > 0.8) & up & uni, f["dfr60_r"] < 0.4, score=f["dfr60_r"], hold=60)
