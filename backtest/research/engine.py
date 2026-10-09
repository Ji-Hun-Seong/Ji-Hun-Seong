"""Research engine: matrix-based daily portfolio simulator for KOSPI200 members."""
import numpy as np
import pandas as pd

DATA = "/tmp/claude-0/bt/k200_prices.csv.gz"
BUY_COST = 0.00015 + 0.001
SELL_COST = 0.00015 + 0.0020 + 0.001
PARK_COST = 0.0005          # ETF 매매 비용(편도, 거래세 면제 가정 + 스프레드)
START = pd.Timestamp("2015-11-01")
IS_END = pd.Timestamp("2020-12-31")


def load(path=None, index_code="KPI200"):
    d = pd.read_csv(path or DATA, dtype={"code": str}, parse_dates=["Date"])
    piv = {f: d.pivot(index="Date", columns="code", values=f) for f in ["Open", "High", "Low", "Close", "Volume"]}
    idx = piv["Close"].pop(index_code)
    for f in piv:
        piv[f] = piv[f].drop(columns=index_code, errors="ignore")
    return piv, idx


def rsi(c, n):
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def features(piv, idx):
    C, O = piv["Close"], piv["Open"]
    f = {"C": C, "O": O}
    mid = C.rolling(20).mean(); sd = C.rolling(20).std()
    f["mid"], f["up"], f["lo"] = mid, mid + 2 * sd, mid - 2 * sd
    f["pb"] = (C - f["lo"]) / (4 * sd)                          # %b
    f["bw"] = 4 * sd / mid                                      # bandwidth
    f["bw_q"] = f["bw"].rolling(250, min_periods=120).rank(pct=True)
    f["rsi2"], f["rsi3"], f["rsi14"] = rsi(C, 2), rsi(C, 3), rsi(C, 14)
    f["ma5"], f["ma50"], f["ma200"] = C.rolling(5).mean(), C.rolling(50).mean(), C.rolling(200).mean()
    f["mom"] = C.shift(5) / C.shift(126) - 1                     # 6개월 모멘텀(최근 1주 제외)
    f["mom_rank"] = f["mom"].rank(axis=1, pct=True)
    f["tv"] = (C * piv["Volume"]).rolling(20).mean()            # 거래대금
    ima200 = idx.rolling(200).mean()
    f["regime"] = (idx > ima200)
    f["idx"] = idx
    return f


def simulate(f, entry, score, exit_sig, max_pos=10, hold=10, stop=None, regime=False,
             park=False, start=START, end=None, ascending=True):
    """entry/exit_sig: bool DataFrame(dates×codes) at close. score: ranking (ascending=True → 낮을수록 우선)."""
    C, O = f["C"], f["O"]
    dates = C.index[(C.index >= start) & ((C.index <= end) if end is not None else True)]
    codes = C.columns
    Cv, Ov = C.reindex(dates).values, O.reindex(dates).values
    Ev = entry.reindex(dates).fillna(False).values.astype(bool)
    if regime:
        Ev &= f["regime"].reindex(dates).fillna(False).values[:, None]
    Xv = exit_sig.reindex(dates).fillna(False).values.astype(bool)
    Sv = score.reindex(dates).values
    ir = f["idx"].pct_change().reindex(dates).fillna(0).values
    rg = f["regime"].reindex(dates).fillna(False).values
    cash, park_amt = 1.0, 0.0
    pos = {}            # j -> [shares, cost, entry_px, days]
    pend_buy, pend_sell = [], set()
    eq_curve, expo, trades = np.empty(len(dates)), np.empty(len(dates)), []
    last_close = np.full(len(codes), np.nan)
    for t in range(len(dates)):
        cl = Cv[t]; op = Ov[t]
        valid = ~np.isnan(cl)
        last_close[valid] = cl[valid]
        if park:
            park_amt *= 1 + ir[t]
            if park == "smart" and not rg[t] and park_amt > 0:   # 시장필터 꺼지면 파킹 해제
                cash += park_amt * (1 - PARK_COST); park_amt = 0.0
        # sells at open
        for j in list(pend_sell):
            if np.isnan(op[j]) or op[j] <= 0:
                continue
            sh, cost, epx, days = pos.pop(j)
            proceeds = sh * op[j] * (1 - SELL_COST)
            cash += proceeds
            trades.append((proceeds / cost - 1, days))
            pend_sell.discard(j)
        # buys at open
        if pend_buy:
            equity = cash + park_amt + sum(p[0] * last_close[j] for j, p in pos.items())
            for j in pend_buy:
                if len(pos) >= max_pos:
                    break
                if j in pos or np.isnan(op[j]) or op[j] <= 0:
                    continue
                budget = equity / max_pos
                avail = cash + (park_amt * (1 - PARK_COST) if park else 0)
                budget = min(budget, avail)
                if budget <= 1e-9:
                    break
                if budget > cash:          # 파킹에서 꺼냄
                    need = budget - cash
                    park_amt -= need / (1 - PARK_COST)
                    cash += need
                cash -= budget
                pos[j] = [budget / (op[j] * (1 + BUY_COST)), budget, op[j], 0]
        pend_buy = []
        # park idle cash
        if park and cash > 1e-9 and (park != "smart" or rg[t]):
            park_amt += cash * (1 - PARK_COST); cash = 0.0
        # close evaluation
        for j, p in pos.items():
            if np.isnan(cl[j]):
                continue
            p[3] += 1
            if Xv[t, j] or p[3] >= hold or (stop is not None and cl[j] <= p[2] * (1 - stop)):
                pend_sell.add(j)
        if len(pos) - len(pend_sell) < max_pos:
            cand = np.where(Ev[t] & valid)[0]
            cand = [j for j in cand if j not in pos]
            if cand:
                s = Sv[t, cand]
                s = np.where(np.isnan(s), np.inf if ascending else -np.inf, s)
                order = np.argsort(s if ascending else -s, kind="stable")
                pend_buy = [cand[k] for k in order]
        hold_val = sum(p[0] * last_close[j] for j, p in pos.items())
        eq = cash + park_amt + hold_val
        eq_curve[t] = eq
        expo[t] = hold_val / eq
    eq = pd.Series(eq_curve, index=dates)
    tr = pd.DataFrame(trades, columns=["ret", "days"])
    return eq, pd.Series(expo, index=dates), tr


def metrics(eq, expo=None, tr=None):
    r = eq.pct_change().dropna()
    yrs = (eq.index[-1] - eq.index[0]).days / 365.25
    m = {"CAGR": (eq.iloc[-1] / eq.iloc[0]) ** (1 / yrs) - 1,
         "MDD": (eq / eq.cummax() - 1).min(),
         "Sharpe": r.mean() / r.std() * np.sqrt(250) if r.std() > 0 else np.nan}
    if expo is not None:
        m["Expo"] = expo.mean()
    if tr is not None and len(tr):
        m.update({"N": len(tr), "Win": (tr.ret > 0).mean(), "AvgTr": tr.ret.mean(), "Days": tr.days.mean()})
    return m


def split_metrics(eq, expo, tr_all=None):
    out = {}
    for name, a, b in [("ALL", None, None), ("IS", None, IS_END), ("OOS", IS_END + pd.Timedelta(days=1), None)]:
        e = eq[(eq.index >= a) if a is not None else slice(None)] if a is not None else eq
        if b is not None:
            e = e[e.index <= b]
        x = expo.reindex(e.index)
        out[name] = metrics(e, x)
    if tr_all is not None:
        out["ALL"].update(metrics(eq, expo, tr_all))
    return out
