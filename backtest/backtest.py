"""
backtest.py — 코스피200 ∩ 가치주 20선에 볼린저밴드+RSI 스윙 전략 백테스트

    python backtest/backtest.py                 # 결과를 backtest/results/ 에 저장
    python backtest/backtest.py --telegram      # 요약을 텔레그램으로도 전송(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)

전략(일봉, 종가에 신호 → 다음 날 시가에 체결)
  매수: 종가 < 볼린저 하단(20일, 2σ) AND RSI(14) < 30 [AND 종가 > 200일선 — 추세 필터 버전만]
  매도: 종가 ≥ 볼린저 중심선 OR RSI ≥ 55 OR 10거래일 보유 OR 종가 ≤ 매수가 −8%  (먼저 오는 것)
  자금: 최대 5종목, 신호 당일 평가액의 1/5씩. 같은 날 신호가 넘치면 RSI 낮은 순.
  비용: 매수 수수료 0.015% + 슬리피지 0.1%, 매도 수수료 0.015% + 거래세 0.20% + 슬리피지 0.1%

주의: 종목군은 '오늘' 기준 코스피200과 '오늘' 기준 20선이다. 과거에는 이 종목들을 미리 알 수 없었으므로
(생존·선정 편향) 결과는 낙관적으로 나온다. 전략끼리, 그리고 같은 종목 단순보유와 비교하는 용도로 볼 것.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import date

import numpy as np
import pandas as pd
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "results")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36"}

START = "2015-01-01"
BUY_COST = 0.00015 + 0.001
SELL_COST = 0.00015 + 0.0020 + 0.001
MAX_POS = 5
HOLD_DAYS = 10
STOP = 0.08


# ---------------------------------------------------------------------------
# 데이터
# ---------------------------------------------------------------------------
def kospi200_codes() -> dict[str, str]:
    """코스피200 편입종목(코드→이름). 네이버 → pykrx 순으로 시도."""
    try:
        out = {}
        for page in range(1, 16):
            r = requests.get("https://m.stock.naver.com/api/index/KPI200/enrollStocks",
                             params={"page": page, "pageSize": 20}, headers=UA, timeout=20)
            j = r.json()
            items = j.get("stocks", j) if isinstance(j, dict) else j
            new = {it["itemCode"]: it.get("stockName", "") for it in items if it.get("itemCode") not in out}
            if not new:
                break
            out.update(new)
        if len(out) >= 150:
            return out
        print("모바일 코스피200", len(out))
    except Exception as e:
        print("모바일 코스피200 실패:", repr(e))
    try:
        return _k200_naver()
    except Exception as e:
        print("네이버 PC 코스피200 실패:", repr(e))
    from pykrx import stock
    codes = stock.get_index_portfolio_deposit_file("1028")
    if len(codes) < 150:
        raise RuntimeError(f"pykrx 코스피200 {len(codes)}개")
    return {c: stock.get_market_ticker_name(c) for c in codes}


def _k200_naver() -> dict[str, str]:
    out = {}
    for page in range(1, 25):
        r = requests.get("https://finance.naver.com/sise/entryJongmok.naver",
                         params={"type": "KPI200", "page": page}, headers=UA, timeout=20)
        r.encoding = "euc-kr"
        found = re.findall(r'code=(\d{6})[^>]*>\s*([^<]+?)\s*</a>', r.text)
        if page == 1 and not found:
            i = r.text.find("code=")
            print("네이버 응답", r.status_code, len(r.text), repr(r.text[max(0, i - 200):i + 300] if i >= 0 else r.text[:600]))
        new = {c: n.strip() for c, n in found if c not in out}
        if not new:
            break
        out.update(new)
        time.sleep(0.2)
    if len(out) < 150:
        raise RuntimeError(f"코스피200 목록이 {len(out)}개만 잡힘 — 페이지 구조 변경 의심")
    return out


def prices(code: str, start=START) -> pd.DataFrame:
    """일봉(수정주가). 네이버 실패 시 FinanceDataReader."""
    try:
        return _prices_naver(code, start)
    except Exception as e:
        import FinanceDataReader as fdr
        df = fdr.DataReader("KS200" if code == "KPI200" else code, start)
        if df.empty:
            raise RuntimeError(f"{code} 시세 없음 (네이버: {e!r})")
        df = df[["Open", "High", "Low", "Close", "Volume"]].astype(float)
        df = df[df["Close"] > 0]
        df.loc[df["Open"] <= 0, "Open"] = df["Close"]
        return df


def _prices_naver(code: str, start=START) -> pd.DataFrame:
    r = requests.get("https://api.finance.naver.com/siseJson.naver",
                     params={"symbol": code, "requestType": 1, "timeframe": "day",
                             "startTime": start.replace("-", ""),
                             "endTime": date.today().strftime("%Y%m%d")},
                     headers=UA, timeout=30)
    rows = re.findall(r'\["(\d{8})",\s*([\d.]+),\s*([\d.]+),\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)', r.text)
    if not rows:
        raise RuntimeError(f"{code} 시세 없음")
    df = pd.DataFrame(rows, columns=["Date", "Open", "High", "Low", "Close", "Volume"])
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date").astype(float)
    df = df[df["Close"] > 0]
    df.loc[df["Open"] <= 0, "Open"] = df["Close"]      # 시가 0(거래정지 등)은 종가로
    return df


def load_picks(path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    items = data["picks"] if isinstance(data, dict) and "picks" in data else data
    out = []
    for it in items:
        row = it.get("row", it)
        out.append({"name": row.get("name") or it.get("name"), "ticker": str(row.get("ticker") or it.get("ticker")).zfill(6)})
    return out


# ---------------------------------------------------------------------------
# 지표·신호
# ---------------------------------------------------------------------------
def rsi(close: pd.Series, n=14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def indicators(df: pd.DataFrame) -> pd.DataFrame:
    c = df["Close"]
    mid = c.rolling(20).mean()
    sd = c.rolling(20).std()
    return df.assign(mid=mid, lower=mid - 2 * sd, rsi=rsi(c), ma200=c.rolling(200).mean())


# ---------------------------------------------------------------------------
# 포트폴리오 시뮬레이션
# ---------------------------------------------------------------------------
def simulate(data: dict[str, pd.DataFrame], trend_filter: bool):
    dates = sorted(set().union(*[d.index for d in data.values()]))
    dates = [d for d in dates if d >= pd.Timestamp(START) + pd.Timedelta(days=300)]   # 200일선 워밍업
    cash, pos, trades, curve = 1.0, {}, [], []
    pending_buy, pending_sell = [], []

    for t in dates:
        # 1) 어제 신호를 오늘 시가에 체결
        for code in pending_sell:
            df = data[code]
            if t not in df.index:
                continue
            p = pos.pop(code)
            px = df.at[t, "Open"]
            proceeds = p["shares"] * px * (1 - SELL_COST)
            cash += proceeds
            trades.append({"code": code, "entry": p["date"].date().isoformat(), "exit": t.date().isoformat(),
                           "days": p["days"], "ret": proceeds / p["cost"] - 1, "why": p["why"]})
        pending_sell = [c for c in pending_sell if c in pos]

        equity_open = cash + sum(p["shares"] * data[c]["Close"].asof(t) for c, p in pos.items())
        for code in pending_buy:
            if len(pos) >= MAX_POS or code in pos:
                continue
            df = data[code]
            if t not in df.index:
                continue
            budget = min(cash, equity_open / MAX_POS)
            if budget <= 0:
                break
            px = df.at[t, "Open"] * (1 + BUY_COST)
            pos[code] = {"shares": budget / px, "cost": budget, "date": t, "entry_px": df.at[t, "Open"], "days": 0, "why": ""}
            cash -= budget
        pending_buy = []

        # 2) 오늘 종가로 평가·신호
        for code, p in pos.items():
            df = data[code]
            if t not in df.index:
                continue
            p["days"] += 1
            r = df.loc[t]
            why = ("stop" if r.Close <= p["entry_px"] * (1 - STOP) else
                   "mid" if r.Close >= r.mid else
                   "rsi" if r.rsi >= 55 else
                   "time" if p["days"] >= HOLD_DAYS else "")
            if why:
                p["why"] = why
                pending_sell.append(code)

        cands = []
        for code, df in data.items():
            if code in pos or t not in df.index:
                continue
            r = df.loc[t]
            if np.isnan(r.lower) or np.isnan(r.rsi):
                continue
            ok = r.Close < r.lower and r.rsi < 30
            if trend_filter:
                ok = ok and not np.isnan(r.ma200) and r.Close > r.ma200
            if ok:
                cands.append((r.rsi, code))
        pending_buy = [c for _, c in sorted(cands)]

        equity = cash + sum(p["shares"] * data[c]["Close"].asof(t) for c, p in pos.items())
        curve.append((t, equity, len(pos)))

    eq = pd.DataFrame(curve, columns=["date", "equity", "npos"]).set_index("date")
    return eq, pd.DataFrame(trades)


def buy_hold(data: dict[str, pd.DataFrame], start) -> pd.Series:
    """같은 종목 동일비중 단순보유(매일 리밸런싱 없이 시작일 균등 매수)."""
    closes = pd.DataFrame({c: d["Close"] for c, d in data.items()}).ffill()
    closes = closes[closes.index >= start]
    first = closes.apply(lambda s: s.first_valid_index())
    parts = []
    for c in closes:
        s = closes[c] / closes.at[first[c], c]
        parts.append(s.where(closes.index >= first[c], 1.0))   # 상장 전엔 현금(1.0)
    return pd.concat(parts, axis=1).mean(axis=1)


def stats(equity: pd.Series, trades: pd.DataFrame | None = None, npos: pd.Series | None = None) -> dict:
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1
    mdd = (equity / equity.cummax() - 1).min()
    out = {"CAGR": cagr, "MDD": mdd, "총수익": equity.iloc[-1] / equity.iloc[0] - 1}
    if trades is not None:
        n = len(trades)
        out.update({"거래수": n,
                    "승률": (trades["ret"] > 0).mean() if n else np.nan,
                    "평균거래수익": trades["ret"].mean() if n else np.nan,
                    "평균보유일": trades["days"].mean() if n else np.nan})
    if npos is not None:
        out["투자비중"] = (npos / MAX_POS).mean()
    return out


def fmt(s: dict) -> str:
    parts = [f"CAGR {s['CAGR']:+.1%}", f"MDD {s['MDD']:.1%}", f"총 {s['총수익']:+.0%}"]
    if "거래수" in s:
        parts += [f"거래 {s['거래수']}회", f"승률 {s['승률']:.0%}" if s["거래수"] else "승률 -",
                  f"건당 {s['평균거래수익']:+.2%}" if s["거래수"] else "", f"평균 {s['평균보유일']:.1f}일" if s["거래수"] else ""]
    if "투자비중" in s:
        parts.append(f"평균 투자비중 {s['투자비중']:.0%}")
    return " · ".join(p for p in parts if p)


# ---------------------------------------------------------------------------
def run(picks_path, telegram=False):
    picks = load_picks(picks_path)
    k200 = kospi200_codes()
    inter = [p for p in picks if p["ticker"] in k200]
    print(f"20선 {len(picks)}개, 코스피200 {len(k200)}개, 교집합 {len(inter)}개: {', '.join(p['name'] for p in inter)}")

    def fetch(codes):
        d = {}
        for c in codes:
            try:
                d[c] = indicators(prices(c))
            except Exception as e:
                print("skip", c, e)
            time.sleep(0.15)
        return d

    inter_data = fetch([p["ticker"] for p in inter])
    k200_data = fetch(list(k200))
    names = {**{c: n for c, n in k200.items()}, **{p["ticker"]: p["name"] for p in picks}}

    results, lines = {}, []
    os.makedirs(OUT, exist_ok=True)
    for label, data in [("교집합", inter_data), ("코스피200 전체", k200_data)]:
        if not data:
            continue
        for tf in (True, False):
            key = f"{label} · {'200일선 필터' if tf else '필터 없음'}"
            eq, tr = simulate(data, tf)
            s = stats(eq["equity"], tr, eq["npos"])
            results[key] = s
            lines.append(f"• {key}\n  {fmt(s)}")
            if not tr.empty:
                tr.assign(name=tr["code"].map(names)).to_csv(
                    os.path.join(OUT, f"trades_{label.replace(' ', '')}_{'trend' if tf else 'nofilter'}.csv"),
                    index=False, encoding="utf-8-sig")
            start = eq.index[0]
        bh = buy_hold(data, start)
        s = stats(bh)
        results[f"{label} · 단순보유"] = s
        lines.append(f"• {label} · 단순보유(동일비중)\n  {fmt(s)}")

    try:
        idx = prices("KPI200")
        idx = idx[idx.index >= start]["Close"]
        results["코스피200 지수"] = stats(idx)
        lines.append(f"• 코스피200 지수\n  {fmt(results['코스피200 지수'])}")
    except Exception as e:
        print("index skip", e)

    period = f"{start.date()} ~ {date.today()}"
    header = (f"📊 BB+RSI 백테스트 ({period})\n"
              f"교집합 {len(inter)}종목: {', '.join(p['name'] for p in inter) or '없음'}\n"
              f"비용 반영(매도 거래세 0.20% 등), 최대 {MAX_POS}종목\n")
    footer = "\n⚠️ 오늘 기준 종목군이라 과거 성과는 낙관적으로 나옴(생존·선정 편향)"
    text = header + "\n" + "\n".join(lines) + footer
    print(text)

    with open(os.path.join(OUT, "summary.txt"), "w", encoding="utf-8") as f:
        f.write(text + "\n")
    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as f:
        json.dump({"period": period, "intersection": inter, "kospi200_count": len(k200),
                   "results": {k: {kk: (None if isinstance(v, float) and np.isnan(v) else float(v))
                                   for kk, v in s.items()} for k, s in results.items()}},
                  f, ensure_ascii=False, indent=2)

    if telegram:
        tok, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
        if tok and chat:
            r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                              data={"chat_id": chat, "text": text}, timeout=20)
            print("telegram", r.status_code, r.text[:200])
        else:
            print("텔레그램 시크릿 없음 — 전송 생략")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--picks", default=os.path.join(ROOT, "value-bot", "picks.json"))
    ap.add_argument("--telegram", action="store_true")
    a = ap.parse_args()
    run(a.picks, a.telegram)
