"""7차-3: 파킹 vs 현금 — 연도별·투자비중·종목 수 바꿔 현금 효율 높이기"""
exec(open("kr10_park.py").read().split('print(f"{\'\':52s}')[0])
a = assets["TIGER 나스닥100(133690, 원화)"].ffill().bfill()
cash = assets["현금(연 2%)"]
curves, expos = {}, {}
for name, asset, mp in [("현금 10종목", cash, 10), ("현금 5종목", cash, 5), ("현금 3종목", cash, 3), ("나스닥100 파킹 10종목", a, 10)]:
    g = dict(f); g["idx"] = asset; g["regime"] = pd.Series(True, index=dates)
    eq, ex, tr = simulate(g, entry=ev, score=rnd, max_pos=mp, exit_sig=f["rsi14"] > 70, hold=10, park="smart")
    curves[name] = eq; expos[name] = ex
    row(name, eq)
    print(f"   주식 투자비중 평균 {ex.loc[START:].mean():.0%}, 거래 {len(tr)}건, 건당 평균 {tr.ret.mean():+.2%}, 승률 {(tr.ret > 0).mean():.0%}")
yr = pd.DataFrame(curves).loc[START:].resample("YE").last().pct_change().dropna()
yr["나스닥100만 보유"] = (a.loc[START:].resample("YE").last().pct_change()).reindex(yr.index)
yr.index = yr.index.year
print(yr.T.map(lambda v: f"{v:+.0%}").to_string())
# 하락장 구간 비교
for nm, s, e in [("2018 하락장", "2018-01-01", "2018-12-31"), ("2020 코로나 2~3월", "2020-02-14", "2020-03-31"), ("2022 하락장", "2022-01-01", "2022-12-31")]:
    print(nm, " | ".join(f"{k} {curves[k].loc[e:].iloc[0] / curves[k].loc[s:].iloc[0] - 1:+.0%}" for k in curves))
