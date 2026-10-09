import numpy as np, pandas as pd
from engine import rsi, metrics, START, IS_END
def load_idx(path, code):
    d = pd.read_csv(path, dtype={"code": str}, parse_dates=["Date"])
    d = d[d.code == code].set_index("Date").sort_index()
    return d[["Open","High","Low","Close"]].astype(float)
def feats(d):
    c = d.Close; mid = c.rolling(20).mean(); sd = c.rolling(20).std()
    return pd.DataFrame({"C": c, "mid": mid, "pb": (c-(mid-2*sd))/(4*sd), "rsi2": rsi(c,2), "rsi14": rsi(c,14),
                         "ma5": c.rolling(5).mean(), "ma200": c.rolling(200).mean()})
def run(x, rule, cost, cash_yield=0.02, lev_cost=0.03):
    w = np.zeros(len(x)); state = {"dip": False, "days": 0}
    for t in range(len(x)):
        w[t] = rule(x.iloc[t], state)
    w = pd.Series(w, index=x.index)
    r = x.C.pct_change().fillna(0)
    wl = w.shift(1).fillna(0)
    ret = wl * r + (1 - wl).clip(lower=0) * cash_yield/252 - (wl - 1).clip(lower=0) * lev_cost/252 - (w.diff().abs().fillna(0)) * cost
    eq = (1 + ret).loc[START:].cumprod()
    return eq, wl.loc[START:]
def R_bh(r, s): return 1.0
def R_trend(r, s): return 1.0 if r.C > r.ma200 else 0.0
def dip_update(r, s, entry, exit_, maxd=10):
    if s["dip"]:
        s["days"] += 1
        if exit_(r) or s["days"] >= maxd: s["dip"] = False
    elif entry(r): s["dip"] = True; s["days"] = 0
    return s["dip"]
E = lambda r: r.rsi2 < 10 and r.pb < 0.2          # BB 하단권 + RSI2 과매도
X = lambda r: r.rsi2 > 70 or r.C > r.ma5
def R_trend_dip(r, s):        # 200일선 위면 보유, 아래면 현금이되 BB/RSI 과매도 반등만 짧게 매매
    d = dip_update(r, s, E, X)
    return 1.0 if (r.C > r.ma200 or d) else 0.0
def R_bh_lever(r, s):         # 항상 보유 + 200일선 위 BB/RSI 눌림에서 1.5배
    d = dip_update(r, s, lambda r: E(r) and r.C > r.ma200, X)
    return 1.5 if d else 1.0
def R_trend_lever(r, s):      # 추세 + 반등 + 눌림 1.5배
    d = dip_update(r, s, E, X)
    if r.C > r.ma200: return 1.5 if d else 1.0
    return 1.0 if d else 0.0
def R_bbrsi_trend(r, s):      # BB/RSI만으로 추세 판단: 중심선 위 & RSI14>50 이면 보유, 하단권 & RSI14<40 이면 정리
    if r.C > r.mid and r.rsi14 > 50: s["in"] = True
    elif r.pb < 0.1 and r.rsi14 < 40: s["in"] = False
    return 1.0 if s.get("in", True) else 0.0
RULES = {"단순보유": R_bh, "200일선 추세": R_trend, "추세+BB/RSI 반등": R_trend_dip,
         "보유+BB/RSI 눌림 1.5배": R_bh_lever, "추세+반등+눌림 1.5배": R_trend_lever, "BB/RSI 추세(중심선·RSI50)": R_bbrsi_trend}
def report(name, d, cost):
    x = feats(d); print(f"\n== {name} ==")
    out = {}
    for k, rule in RULES.items():
        eq, wl = run(x, rule, cost)
        ms = {}
        for p, a, b in [("ALL", None, None), ("IS", None, IS_END), ("OOS", IS_END + pd.Timedelta(days=1), None)]:
            e = eq.loc[a:b]; ms[p] = metrics(e / e.iloc[0])
        out[k] = (eq, ms)
        print(f"{k:24s} | 전체 {ms['ALL']['CAGR']:+.1%} MDD {ms['ALL']['MDD']:+.1%} Sh {ms['ALL']['Sharpe']:.2f} 평균비중 {wl.mean():.2f} 매매 {int((wl.diff().abs()>0).sum())}회 | IS {ms['IS']['CAGR']:+.1%} Sh {ms['IS']['Sharpe']:.2f} MDD {ms['IS']['MDD']:+.1%} | OOS {ms['OOS']['CAGR']:+.1%} Sh {ms['OOS']['Sharpe']:.2f} MDD {ms['OOS']['MDD']:+.1%}")
    return out
if __name__ == "__main__":
    import sys
    kr = report("코스피200 지수 (ETF 비용 0.05%)", load_idx("/home/claude/ji-hun-seong/backtest/data/k200_prices.csv.gz", "KPI200"), 0.0005)
    us = report("S&P500 (SPY, 비용 0.15%)", load_idx("/tmp/claude-0/bt/us_prices.csv.gz", "SPY"), 0.0015)
