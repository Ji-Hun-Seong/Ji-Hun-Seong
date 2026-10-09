exec(open("fr.py").read().split("# ---------- T1")[0])
names = pd.read_csv("/tmp/claude-0/btkr/kospi_all_members.csv", dtype=str).set_index("code")["name"]
t = C.index[-1]
w_tv = f["tv"].where(uni)
agg = (f["dfr20"] * w_tv).sum(axis=1) / w_tv.where(f["dfr20"].notna()).sum(axis=1)
ma200 = idx.rolling(200).mean()
print("기준일", t.date(), "| 코스피200", round(idx.loc[t], 1), "200일선", round(ma200.loc[t], 1), "→ 추세", "위" if idx.loc[t] > ma200.loc[t] else "아래",
      "| 시장 외국인 20일 순매수(가중 보유율 변화)", f"{agg.loc[t]:+.3f}%p", "→", "순매수" if agg.loc[t] > 0 else "순매도")
print("최근 10거래일 시장 외국인 20일 순매수:", " ".join(f"{v:+.2f}" for v in agg.iloc[-10:]))
sq = f["bw_q"].rolling(5).min() < 0.2
sig = sq & (C > f["up"]) & (f["rsi14"] > 60) & (f["ma50"] > f["ma200"]) & uni
for d in C.index[-5:]:
    s = sig.loc[d]; s = s[s].index
    if len(s):
        print(d.date(), "스퀴즈 돌파:", ", ".join(f"{names.get(c,c)}(RSI {f['rsi14'].loc[d,c]:.0f}, 외국인60일 {f['dfr60'].loc[d,c]:+.1f}%p)" for c in s))
top = f["dfr60"].loc[t].where(uni.loc[t]).dropna().sort_values(ascending=False).head(10)
print("60일 외국인 순매수 상위10(유니버스):", ", ".join(f"{names.get(c,c)} {v:+.1f}%p" for c, v in top.items()))
