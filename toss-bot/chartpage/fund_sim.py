"""🏦 대가 TOP 10 모의 펀드 — 실제 국내 주식형 공모펀드처럼 기준가를 매일 산출한다.

펀드 2개: 💎 가치주 TOP 10 · 🚀 성장주 TOP 10 (발굴 › 대가 › 🇰🇷 한국 탭과 같은 걸러내기·순위)
  · 설정: 1억원, 최초 기준가 1,000.00원 (1좌 = 1원, 기준가는 1,000좌당 가격)
  · 매일 장 마감 후(서버 cron 16:10) 그날 종가로 평가 → 기준가 산출
      자산총액 = 주식 평가액 + 현금 + 미수배당금
      부채총액 = 미지급 보수 (운용·판매·수탁·사무관리 — 전일 순자산 × 연 보수율 ÷ 365 × 경과일수, 매 분기 첫 산출일에 지급)
      순자산총액 = 자산총액 − 부채총액,  기준가 = 순자산총액 ÷ 총좌수 × 1,000
  · 매월 첫 거래일에 그날 TOP 10으로 교체 + 동일비중(각 9.9%, 현금 1%) 맞춤 — 매매수수료·증권거래세 반영, 정수 주
  · 배당: 배당락일에 미수배당금(세전, 펀드는 원천징수 없음 가정) → 30일 뒤 현금 입금
  · 비교지수: 코스피
주문은 내지 않는다(종이 위의 펀드). 상태: toss-bot/state/funds.json

🇺🇸 미국 버전 2개: 💎 미국 가치주 TOP 10 · 🚀 미국 성장주 TOP 10 (발굴 › 대가 › 🇺🇸 미국 탭과 같은 규칙)
  · 국내에서 파는 '해외주식형 공모펀드(환노출형)'처럼 원화로 설정·기준가 산출 — 종가(달러) × 그날 원/달러 환율
  · 미국 장 마감(한국 아침 5~6시) 뒤 서버 cron 07:10(화~토)에 직전 미국 거래일로 산출
  · 매매수수료 0.25%(해외주식) · 거래세 없음 · 배당은 미국 원천징수 15% 뗀 금액 · 비교지수 S&P 500(원화 환산)

사용:  python chartpage/fund_sim.py run        # 오늘 기준가 산출 (첫 실행이면 오늘 설정)
       python chartpage/fund_sim.py run-us     # 🇺🇸 직전 미국 거래일 기준가 산출
       python chartpage/fund_sim.py show       # 요약 출력
       python chartpage/fund_sim.py reset      # 처음부터 다시 (funds.json 백업 후 삭제)
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
PATH = os.path.join(os.path.dirname(HERE), "state", "funds.json")

SEED = 100_000_000                 # 설정액 1억원
N = 10                             # 편입 종목 수
CASH_BUF = 0.01                    # 현금 1% 남김 (환매·보수 지급 대비)
FEES = {"운용": 0.0070, "판매": 0.0060, "수탁": 0.0003, "사무관리": 0.0002}   # 연율 — 국내 액티브 주식형 A클래스 수준
COMMISSION = 0.0005                # 매매수수료 (매수·매도 각각)
SELL_TAX = 0.0020                  # 증권거래세+농특세 (2026년 코스피 0.20% 가정, 매도 때만)
DIV_PAY_DAYS = 30                  # 배당락 → 입금까지

FUNDS = {
    "value": {"name": "💎 대가 가치주 TOP 10", "desc": "가치 대가 점수 순 · PBR 0~2 · PER 10 이하 · 버핏 10점↑ · 매출·순이익 꾸준히 증가",
              "market": "kr", "kind": "value"},
    "growth": {"name": "🚀 대가 성장주 TOP 10", "desc": "성장 대가 점수 순 · 시총 10조 미만 · PBR 0~10 · 린치 10점↑ · 매출·순이익 꾸준히 증가",
               "market": "kr", "kind": "growth"},
    "us_value": {"name": "🇺🇸💎 미국 대가 가치주 TOP 10", "desc": "가치 대가 점수 순 · PBR 0~2 · PER 30 이하 · 버핏 10점↑ · 매출·순이익 꾸준히 증가 · 원화 환산(환노출)",
                 "market": "us", "kind": "value"},
    "us_growth": {"name": "🇺🇸🚀 미국 대가 성장주 TOP 10", "desc": "성장 대가 점수 순 · PBR 0~10 · 린치 10점↑ · 매출·순이익 꾸준히 증가 · 원화 환산(환노출)",
                  "market": "us", "kind": "growth"},
}
MKT = {   # 시장별: 매매비용 · 비교지수 · 배당 원천징수
    "kr": {"commission": COMMISSION, "sell_tax": SELL_TAX, "bench": "코스피", "wht": 0.0, "per_max": 10, "growth_mcap_max": 100000},
    "us": {"commission": 0.0025, "sell_tax": 0.0, "bench": "S&P 500(원화)", "wht": 0.15, "per_max": 30, "growth_mcap_max": None},
}


# ── 종목 고르기: 화면(static/index.html 발굴 › 대가 탭)과 같은 규칙 ─────────────────
def _ok_steady(x):
    s = x.get("steady") or {}
    return s.get("ok") is not False


def is_value(x, market: str = "kr") -> bool:
    pbr, per, h = x.get("pbr"), x.get("per"), x.get("heroes") or {}
    return (x.get("vgrade") != "no" and (pbr is None or 0 < pbr <= 2) and (per is None or per <= MKT[market]["per_max"])
            and (h.get("buffett") is None or h["buffett"] >= 10) and _ok_steady(x)
            and (x.get("style") == "both" or (x.get("value") or -1) >= (x.get("growth") or -1)))


def is_growth(x, market: str = "kr") -> bool:
    pbr, h, mc, cap = x.get("pbr"), x.get("heroes") or {}, x.get("mcap_eok"), MKT[market]["growth_mcap_max"]
    return (x.get("ggrade") != "no" and (h.get("lynch") is None or h["lynch"] >= 10) and (pbr is None or 0 < pbr <= 10)
            and _ok_steady(x) and (cap is None or mc is None or mc < cap)
            and (x.get("style") == "both" or (x.get("growth") or -1) > (x.get("value") or -1)))


def top10(kind: str, items: list[dict], market: str = "kr") -> list[dict]:
    f, key = (is_value, "value") if kind == "value" else (is_growth, "growth")
    xs = [x for x in items if x.get("code") and f(x, market)]
    xs.sort(key=lambda x: -(x.get(key) or 0))
    return [{"code": x["code"], "name": x.get("name"), "score": round(x.get(key) or 0, 1), "industry": x.get("industry")} for x in xs[:N]]


def board_items(market: str = "kr") -> list[dict]:
    import hero_db
    if hero_db.PATH is None:                                # 대시보드 밖(cron)에서 돌 때 — 같은 채점 DB 를 읽기만 함
        hero_db.init(os.path.join(os.path.dirname(PATH), "heroes.db"))
    return hero_db.board(market).get("items", [])


# ── 시세 ─────────────────────────────────────────────
def closes(code: str, days: int = 60, market: str = "kr") -> dict:
    """{YYYY-MM-DD: 종가} — 미국은 달러"""
    if market == "us":
        import data_sources as ds
        df = ds.get_ohlcv(code, us=True, rng="3mo")
        return {f"{d:%Y-%m-%d}": float(c) for d, c in zip(df.index, df["close"])}
    import stock_info as si
    df = si.kr_ohlcv(code, days)
    return {f"{d:%Y-%m-%d}": float(c) for d, c in zip(df.index, df["close"])}


def usdkrw() -> dict:
    """{YYYY-MM-DD: 원/달러} — 야후 KRW=X 일별 (그날 값이 없으면 직전 값을 씀)"""
    import data_sources as ds
    try:
        df = ds.get_ohlcv("KRW=X", us=True, rng="3mo")
    except Exception:
        import yfinance as yf
        h = yf.Ticker("KRW=X").history(period="3mo")
        return {f"{d:%Y-%m-%d}": float(c) for d, c in zip(h.index, h["Close"])}
    return {f"{d:%Y-%m-%d}": float(c) for d, c in zip(df.index, df["close"])}


def _asof(series: dict, day: str):
    ks = [k for k in series if k <= day]
    return series[max(ks)] if ks else None


def spx() -> dict:
    try:
        import data_sources as ds
        df = ds.get_ohlcv("^GSPC", us=True, rng="3mo")
        return {f"{d:%Y-%m-%d}": float(c) for d, c in zip(df.index, df["close"])}
    except Exception:
        import yfinance as yf
        h = yf.Ticker("^GSPC").history(period="3mo")
        return {f"{d:%Y-%m-%d}": float(c) for d, c in zip(h.index, h["Close"])}


def kospi(days: int = 60) -> dict:
    try:
        k = closes("KOSPI", days)
        if k and min(k.values()) > 500:
            return k
    except Exception:
        pass
    if True:
        import yfinance as yf
        df = yf.Ticker("^KS11").history(period=f"{max(days, 5)}d")
        return {f"{d:%Y-%m-%d}": float(c) for d, c in zip(df.index, df["Close"])}


def dividends_on(code: str, day: str, market: str = "kr") -> float:
    """그날이 배당락일이면 주당 배당금(원 · 미국은 달러), 아니면 0 — 야후 기준"""
    try:
        import yfinance as yf
        for suf in ((".KS", ".KQ") if market == "kr" else ("",)):
            s = yf.Ticker(code + suf).dividends
            if len(s):
                return float(sum(v for d, v in s.items() if f"{d:%Y-%m-%d}" == day))
    except Exception:
        pass
    return 0.0


# ── 상태 ─────────────────────────────────────────────
def load() -> dict:
    try:
        return json.load(open(PATH, encoding="utf-8"))
    except Exception:
        return {}


def save(st: dict):
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    json.dump(st, open(PATH + ".tmp", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(PATH + ".tmp", PATH)


def new_fund(key: str, day: str) -> dict:
    return {"key": key, **{k: v for k, v in FUNDS[key].items() if k in ("name", "desc")}, "market": FUNDS[key]["market"], "inception": day, "seed": SEED, "units": float(SEED), "cash": float(SEED),
            "payable": 0.0, "fee_paid": 0.0, "fee_quarter": _q(day), "costs": 0.0, "recv": [], "holdings": {},
            "last_rebal": None, "hist": [], "trades": [], "bench0": None}


def _q(day: str) -> str:
    y, m = int(day[:4]), int(day[5:7])
    return f"{y}Q{(m - 1) // 3 + 1}"


def _stock_value(f: dict, px: dict) -> float:
    return sum(h["shares"] * px.get(c, h.get("last_px", 0)) for c, h in f["holdings"].items())


def _recv_total(f: dict) -> float:
    return sum(r["amount"] for r in f["recv"])


def rebalance(f: dict, picks: list[dict], px: dict, day: str, net: float):
    """그날 종가로 TOP 10 동일비중 맞춤. 판 뒤 산다(매도 대금으로 매수). 미국은 px 가 이미 원화 환산 값"""
    M = MKT[f.get("market", "kr")]
    COMMISSION, SELL_TAX = M["commission"], M["sell_tax"]
    want = {p["code"]: p for p in picks if px.get(p["code"])}
    tgt_each = net * (1 - CASH_BUF) / max(len(want), 1)
    trades = []

    def trade(code, name, qty, price, why):
        amt = qty * price
        fee = abs(amt) * COMMISSION + (abs(amt) * SELL_TAX if qty < 0 else 0)
        f["cash"] -= amt + fee
        f["costs"] += fee
        h = f["holdings"].setdefault(code, {"name": name, "shares": 0, "cost": 0.0})
        if qty > 0:
            h["cost"] += amt + fee
        else:
            h["cost"] -= h["cost"] * (-qty / h["shares"]) if h["shares"] else 0
        h["shares"] += qty
        h["last_px"] = price
        if h["shares"] == 0:
            f["holdings"].pop(code, None)
        trades.append({"date": day, "code": code, "name": name, "side": "매수" if qty > 0 else "매도", "qty": abs(qty),
                       "price": price, "amount": round(abs(amt)), "fee": round(fee), "why": why})

    for c in list(f["holdings"]):                          # 1) 편출·비중 축소
        h, p = f["holdings"][c], px.get(c, f["holdings"][c].get("last_px"))
        if not p:
            continue
        if c not in want:
            trade(c, h["name"], -h["shares"], p, "편출")
        else:
            extra = math.floor((h["shares"] * p - tgt_each) / p)
            if extra > 0:
                trade(c, h["name"], -extra, p, "비중 축소")
    for c, pk in want.items():                             # 2) 편입·비중 확대 (현금 안에서)
        p = px[c]
        have = f["holdings"].get(c, {}).get("shares", 0)
        q = math.floor((tgt_each - have * p) / p)
        q = min(q, math.floor(max(f["cash"] - net * CASH_BUF * 0.5, 0) / (p * (1 + COMMISSION))))
        if q > 0:
            trade(c, pk["name"], q, p, "편입" if have == 0 else "비중 확대")
    turnover = sum(t["amount"] for t in trades if t["side"] == "매도") / net if net else 0
    f["trades"] = (f["trades"] + trades)[-400:]
    f["last_rebal"] = day[:7]
    f["picks"] = picks
    return trades, turnover


def run(day: str | None = None, dry: bool = False, market: str = "kr") -> dict:
    """오늘(또는 day) 기준가 산출. 거래일이 아니면 아무것도 안 함.
       미국(market='us'): day 를 안 주면 S&P 500 의 마지막 종가 날짜(= 직전 미국 거래일)"""
    fx = None
    if market == "us":
        sp, fx = spx(), usdkrw()
        today = day or max(sp)
        if today not in sp:
            return {"skip": f"{today} S&P 500 종가 없음 — 미국 휴장"}
        if _asof(fx, today) is None:
            return {"skip": f"{today} 원/달러 환율 없음"}
        kp = {d: v * _asof(fx, d) for d, v in sp.items() if _asof(fx, d)}      # 비교지수도 원화 환산
    else:
        today = day or dt.date.today().isoformat()
        kp = kospi()
        if today not in kp:
            return {"skip": f"{today} 코스피 종가 없음 — 휴장이거나 아직 장 마감 전"}
    rate = _asof(fx, today) if fx else 1.0
    st = load()
    items, picks = None, {}
    out = {}
    for key in [k for k, v in FUNDS.items() if v["market"] == market]:
        f = st.get(key)
        if f and f["hist"] and f["hist"][-1]["date"] >= today:
            out[key] = "이미 산출됨"
            continue
        first = f is None
        if first:
            f = st[key] = new_fund(key, today)
        need_rebal = first or f["last_rebal"] != today[:7]
        if need_rebal and items is None:
            items = board_items(market)
        if need_rebal:
            picks[key] = top10(FUNDS[key]["kind"], items, market)
        codes = set(f["holdings"]) | {p["code"] for p in picks.get(key, [])}
        px = {}
        for c in codes:                                     # 그날 종가 (없으면 직전 가격으로 평가하고 표시)
            try:
                cl = closes(c, market=market)
                if today in cl:
                    px[c] = cl[today] * rate                    # 미국: 달러 종가 × 원/달러 → 원화
            except Exception:
                pass
        # 1) 배당 — 입금 예정일 지난 미수배당은 현금으로, 오늘 배당락은 미수배당으로
        for r in list(f["recv"]):
            if r["pay"] <= today:
                f["cash"] += r["amount"]
                f["recv"].remove(r)
        if not first:
            for c, h in f["holdings"].items():
                dps = dividends_on(c, today, market)
                if dps > 0:
                    pay = (dt.date.fromisoformat(today) + dt.timedelta(days=DIV_PAY_DAYS)).isoformat()
                    amt = h["shares"] * dps * rate * (1 - MKT[market]["wht"])     # 미국: 원천징수 15% 뗀 원화
                    f["recv"].append({"code": c, "name": h["name"], "ex": today, "pay": pay, "dps": dps, "amount": round(amt)})
        # 2) 보수 — 전일 순자산 × 연율 ÷ 365 × 경과일수 (휴일 포함 달력일)
        fee_today = {}
        if not first:
            prev = f["hist"][-1]
            days = (dt.date.fromisoformat(today) - dt.date.fromisoformat(prev["date"])).days
            for k, r in FEES.items():
                fee_today[k] = prev["net"] * r / 365 * days
            f["payable"] += sum(fee_today.values())
            if _q(today) != f["fee_quarter"]:               # 분기 바뀐 첫 산출일에 지난 분기 보수 지급
                f["cash"] -= f["payable"]
                f["fee_paid"] += f["payable"]
                f["payable"] = 0.0
                f["fee_quarter"] = _q(today)
        for c, h in f["holdings"].items():
            if c in px:
                h["last_px"] = px[c]
        # 3) 리밸런싱 (설정일·매월 첫 거래일)
        net_pre = _stock_value(f, px) + f["cash"] + _recv_total(f) - f["payable"]
        trades, turnover = ([], 0.0)
        if need_rebal and picks.get(key):
            trades, turnover = rebalance(f, picks[key], px, today, net_pre)
        # 4) 기준가
        stock = _stock_value(f, px)
        recv = _recv_total(f)
        assets = stock + f["cash"] + recv
        net = assets - f["payable"]
        nav = SEED / f["units"] * 1000 if first else net / f["units"] * 1000      # 설정일은 1,000.00원으로 공고
        if f["bench0"] is None:
            f["bench0"] = kp[today]
        rec = {"date": today, "nav": round(nav, 2), "net": round(net), "assets": round(assets), "stock": round(stock),
               "cash": round(f["cash"]), "recv": round(recv), "payable": round(f["payable"]), "units": round(f["units"]),
               "fee_today": {k: round(v) for k, v in fee_today.items()}, "bench": round(kp[today] / f["bench0"] * 1000, 2),
               "kospi": kp[today], "n": len(f["holdings"]), "stale": sorted(c for c in f["holdings"] if c not in px)}
        if market == "us":
            rec["fx"] = round(rate, 2)
        if trades:
            rec["rebal"] = {"trades": len(trades), "turnover": round(turnover * 100, 1)}
        f["hist"].append(rec)
        out[key] = rec
    if not dry:
        st["updated"] = time.strftime("%Y-%m-%d %H:%M")
        save(st)
    return out


# ── 화면용 ─────────────────────────────────────────────
def summary() -> dict:
    st = load()
    if not st:
        return {"kind": "fund", "funds": [], "note": "아직 설정 전 — 서버에서 python chartpage/fund_sim.py run (장 마감 후)"}
    funds = []
    for key in FUNDS:
        f = st.get(key)
        if not f or not f["hist"]:
            continue
        f.setdefault("market", FUNDS[key]["market"])
        last = f["hist"][-1]
        hold = []
        for c, h in sorted(f["holdings"].items(), key=lambda kv: -kv[1]["shares"] * kv[1].get("last_px", 0)):
            val = h["shares"] * h.get("last_px", 0)
            hold.append({"code": c, "name": h["name"], "shares": h["shares"], "price": h.get("last_px"), "value": round(val),
                         "weight": round(val / last["net"] * 100, 2) if last["net"] else None,
                         "pnl": round((val / h["cost"] - 1) * 100, 2) if h.get("cost") else None})
        funds.append({"key": key, "name": f["name"], "desc": f["desc"], "inception": f["inception"], "seed": f["seed"],
                      "market": f.get("market", "kr"), "bench_name": MKT[f.get("market", "kr")]["bench"],
                      "last": last, "hist": [{"d": r["date"], "nav": r["nav"], "bench": r["bench"]} for r in f["hist"]],
                      "ret": round((last["nav"] / 1000 - 1) * 100, 2), "bench_ret": round((last["bench"] / 1000 - 1) * 100, 2),
                      "holdings": hold, "trades": f["trades"][-30:][::-1], "recv": f["recv"], "fee_paid": round(f["fee_paid"]),
                      "costs": round(f["costs"]), "last_rebal": f["last_rebal"], "picks": f.get("picks", [])})
    return {"kind": "fund", "funds": funds, "updated": st.get("updated"),
            "rules": {"seed": SEED, "n": N, "cash_buf": CASH_BUF, "fees": FEES, "fee_total": round(sum(FEES.values()) * 100, 2),
                      "commission": COMMISSION, "sell_tax": SELL_TAX, "div_pay_days": DIV_PAY_DAYS}}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "show"
    if cmd == "run":
        print(json.dumps(run(sys.argv[2] if len(sys.argv) > 2 else None), ensure_ascii=False, indent=1))
    elif cmd == "run-us":
        print(json.dumps(run(sys.argv[2] if len(sys.argv) > 2 else None, market="us"), ensure_ascii=False, indent=1))
    elif cmd == "reset":
        if os.path.exists(PATH):
            os.replace(PATH, PATH + f".bak{int(time.time())}")
        print("초기화 — 다음 run 에서 새로 설정")
    else:
        s = summary()
        for f in s["funds"]:
            l = f["last"]
            print(f"{f['name']}  {l['date']}  기준가 {l['nav']:,.2f}  ({f['ret']:+.2f}% · 코스피 {f['bench_ret']:+.2f}%)  순자산 {l['net']:,}원")
            for h in f["holdings"]:
                print(f"   {h['name']:<12} {h['weight']:>5}%  {h['shares']:>6}주  {h['pnl'] if h['pnl'] is not None else '-':>6}%")
        print(s.get("note", ""))
