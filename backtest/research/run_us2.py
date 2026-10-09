from us_common import *
print("시점별 구성종목 수(평균):", mem.loc[START:].sum(axis=1).mean().round(0), " 시세 있는 비율:", (mem & C.notna()).loc[START:].sum(axis=1).mean().round(0))
line("SPY", "", split_metrics(bench, pd.Series(1.0, index=bench.index)))
# 동일비중 단순보유 비교: 현재종목 vs 시점별
r = C.pct_change(fill_method=None)
for nm, M in [("현재종목", CUR), ("시점별", mem)]:
    w = M.shift(1).fillna(False) & r.notna()
    ew = (r.where(w).mean(axis=1)).loc[START:].fillna(0)
    line(f"동일비중 보유({nm})", "", split_metrics((1+ew).cumprod(), pd.Series(1.0, index=ew.index)))
for univ, M, mr in [("현재종목", CUR, f["mom_rank"]), ("시점별", mem, mom_rank_pit)]:
    for name, kw in S(mr).items():
        kw = dict(kw); kw["entry"] = kw["entry"] & M
        eq, ex, tr = simulate(f, regime=True, **kw)
        line(name, univ + " R", split_metrics(eq, ex, tr))
