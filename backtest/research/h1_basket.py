import sys, pickle
import numpy as np, pandas as pd
sys.path.insert(0, ".")
from engine import *
piv, idx = load("/tmp/claude-0/btkr/kospi_all.csv.gz", "KPI200")
held, rp, rc, liquid = pickle.load(open("switch.pkl", "rb"))
names = pd.read_csv("/tmp/claude-0/btkr/kospi_all_members.csv", dtype=str).set_index("code")["name"]
C = piv["Close"]
lv = liquid.shift(1).fillna(False)
cost = held.diff().abs().fillna(0) * 2 * (0.00015 + 0.002 + 0.001)
sw = (held * rc + (1 - held) * rp - cost)
def basket(r):   # 동일비중(매일 재조정 근사), 로그수익→단순수익
    x = (np.exp(r) - 1).where(lv).mean(axis=1).loc[START:].fillna(0)
    return (1 + x).cumprod()
res = {"보통주만 보유": basket(rc), "우선주만 보유": basket(rp), "싼 쪽 갈아타기": basket(sw)}
b = idx.loc[START:]; res["코스피200"] = b / b.iloc[0]
for k, eq in res.items():
    m = split_metrics(eq, pd.Series(1.0, index=eq.index))
    print(f"{k:10s} | " + " | ".join(f"{kk} {m[kk]['CAGR']:+.1%} MDD {m[kk]['MDD']:+.1%} Sh {m[kk]['Sharpe']:.2f}" for kk in m))
print("바스켓 평균 종목 수", int(lv.loc[START:].sum(axis=1).mean()))
d = pd.DataFrame(res).resample("YE").last().pct_change(); d.index = d.index.year
print(d.iloc[1:].map(lambda v: f"{v:+.0%}").T.to_string())
# 오늘 신호(2026-10-08): 괴리 BB/RSI
P = C[held.columns]; Cm = C[[p[:5] + "0" for p in held.columns]].set_axis(held.columns, axis=1)
Rr = np.log(P / Cm); rsiR = Rr.apply(lambda s: rsi(np.exp(s), 14))
mid = Rr.rolling(60).mean(); sd = Rr.rolling(60).std(); pb = (Rr - (mid - 2 * sd)) / (4 * sd)
t = Rr.index[-1]
now = pd.DataFrame({"우선주": [names.get(c, c) for c in Rr.columns], "괴리(우/보)": np.exp(Rr.loc[t]).round(3), "%b": pb.loc[t].round(2), "RSI": rsiR.loc[t].round(0), "유동성": liquid.loc[t]}, index=Rr.columns)
print("\n기준일", t.date())
print("고평가(보통주로):", now[(now["%b"] > 1) & (now.RSI > 70) & now["유동성"]].to_string())
print("저평가(우선주 쪽):", now[(now["%b"] < 0) & (now.RSI < 30) & now["유동성"]].to_string())
print("코오롱인더우:", now[now["우선주"].str.contains("코오롱인더")].to_string())
