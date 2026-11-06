"""👤 내 펀드 — 토스 실제 계좌(내가 직접 지정가로 사고판 종목)를 공모펀드처럼 기준가로 산출한다.

  · 설정일 기준가 1,000.00 — 그날 보유 종목을 그날 종가로 평가한 금액이 최초 설정액
  · 매일 장 마감 후(서버 cron 16:10, fund_sim.py run 이 이걸 부름) 계좌 잔고·체결내역을 읽어 기준가 산출
      하루 수익률 r = (오늘 평가액 + 판 돈 − 어제 평가액 − 산 돈) ÷ (어제 평가액 + 산 돈)
      · 산 돈 = 체결금액 + 수수료 + 세금 (펀드에 새로 들어온 돈 = 설정)
      · 판 돈 = 체결금액 − 수수료 − 세금 (펀드에서 나간 돈 = 환매) + 그날 배당락 종목의 배당금
      → 돈을 더 넣거나 빼도 기준가는 안 흔들리고 '종목을 고르고 사고판 실력'만 남음 (시간가중수익률)
      기준가 = 어제 기준가 × (1 + r)
  · 미국 종목은 원화 환산(그날 원/달러), 배당은 원천징수 15% 뗀 금액
  · 비교지수: 코스피 (설정일 = 1,000)
  · 상태: toss-bot/state/my_fund.json — 주문은 내지 않고 계좌를 읽기만 함

사용:  python chartpage/my_fund.py run      # 오늘 기준가 산출 (처음이면 오늘 설정)
       python chartpage/my_fund.py show     # 요약
       python chartpage/my_fund.py reset    # 처음부터 다시 (백업 후 삭제)
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
PATH = os.path.join(ROOT, "state", "my_fund.json")
US_WHT = 0.15
KST = dt.timezone(dt.timedelta(hours=9))


def load() -> dict:
    try:
        return json.load(open(PATH, encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def save(st: dict):
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    json.dump(st, open(PATH + ".tmp", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(PATH + ".tmp", PATH)


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _ts(s):
    """체결 시각 문자열 → aware datetime (없으면 None)"""
    if not s:
        return None
    try:
        t = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=KST)
    except ValueError:
        return None


def holdings(a, fx: float | None) -> dict:
    h = a.holdings() or {}
    out = {}
    for i in h.get("items", []):
        qty, px = _f(i.get("quantity")) or 0, _f(i.get("lastPrice"))
        if qty <= 0 or px is None:
            continue
        us = (i.get("currency") or "KRW").upper() == "USD"
        rate = (fx or 0) if us else 1.0
        out[i["symbol"]] = {"name": i.get("name") or i["symbol"], "qty": qty, "px": px, "us": us,
                            "avg": _f(i.get("averagePurchasePrice")), "val": qty * px * rate}
    return out


def fills_between(a, t0: dt.datetime | None, t1: dt.datetime) -> list[dict]:
    """t0 < 체결시각 <= t1 인 체결 (부분 체결 포함)"""
    import manual_trade as mt
    fr = (t0 or t1).astimezone(KST).date()
    rows, cur, seen = [], None, set()
    for _ in range(10):
        r = a.orders("CLOSED", None, fr.isoformat(), t1.astimezone(KST).date().isoformat(), 100, cur)
        for o in r.get("orders") or []:
            x = mt._order_row(o)
            if x["id"] in seen or not x["filled"]:
                continue
            seen.add(x["id"])
            t = _ts(x.get("filled_at")) or _ts(x.get("at"))
            if t is None or t > t1 or (t0 is not None and t <= t0):
                continue
            rows.append(x)
        cur = r.get("nextCursor")
        if not r.get("hasNext") or not cur:
            break
    rows.sort(key=lambda x: x.get("filled_at") or x.get("at") or "")
    return rows


def run(day: str | None = None) -> dict:
    import bot
    import fund_sim as fs
    now = dt.datetime.now(KST)
    if day and day != now.date().isoformat():              # 지난 날짜로 돌릴 때(시험용): 그날 끝까지의 체결
        now = dt.datetime.fromisoformat(day + "T23:59:59+09:00")
    today = day or now.date().isoformat()
    kp = fs.kospi()
    if today not in kp:
        return {"skip": f"{today} 코스피 종가 없음 — 휴장이거나 아직 장 마감 전"}
    st = load()
    if st.get("hist") and st["hist"][-1]["date"] >= today:
        return {"skip": f"{today} 이미 산출됨"}
    a = bot.api()
    fxs = None
    try:
        fxs = fs.usdkrw()
    except Exception:
        pass
    fx = fs._asof(fxs, today) if fxs else None
    hold = holdings(a, fx)
    if any(h["us"] for h in hold.values()) and not fx:
        return {"skip": "원/달러 환율을 못 받아서 미국 종목을 원화로 못 바꿈 — 다음에 다시"}
    v_end = sum(h["val"] for h in hold.values())

    if not st.get("hist"):                                   # 설정
        st = {"inception": today, "kospi0": kp[today], "cut": now.isoformat(), "trades": [], "divs": [],
              "hist": [{"date": today, "nav": 1000.0, "bench": 1000.0, "kospi": kp[today], "net": round(v_end),
                        "buy": 0, "sell": 0, "r": 0.0, "n": len(hold)}],
              "holdings": hold, "updated": now.strftime("%Y-%m-%d %H:%M")}
        save(st)
        return {"설정": today, "순자산": round(v_end), "종목수": len(hold)}

    prev = st["hist"][-1]
    t0 = _ts(st.get("cut"))
    fl = fills_between(a, t0, now)
    buy = sell = 0.0
    for x in fl:
        rate = (fx or 0) if (x.get("ccy") or "KRW").upper() == "USD" else 1.0
        amt, cost = (x.get("amount") or 0) * rate, ((x.get("fee") or 0) + (x.get("tax") or 0)) * rate
        if x["side"] == "BUY":
            buy += amt + cost
        else:
            sell += amt - cost
        st["trades"].append({"date": today, "at": x.get("filled_at"), "code": x["code"], "side": "매수" if x["side"] == "BUY" else "매도",
                             "qty": x["filled"], "price": x.get("avg"), "amount": round(amt), "cost": round(cost),
                             "name": (hold.get(x["code"]) or st["holdings"].get(x["code"]) or {}).get("name", x["code"]),
                             "us": rate != 1.0})
    # 배당 — 어제 들고 있던 종목이 오늘 배당락이면, 받을 배당금을 펀드 수익으로 (현금이 계좌로 빠져나간 것으로 처리)
    div = 0.0
    for c, h in st["holdings"].items():
        dps = fs.dividends_on(c, today, "us" if h.get("us") else "kr")
        if dps > 0:
            amt = h["qty"] * dps * ((fx or 0) * (1 - US_WHT) if h.get("us") else 1.0)
            div += amt
            st["divs"].append({"date": today, "code": c, "name": h["name"], "dps": dps, "amount": round(amt)})
    v0 = prev["net"]
    denom = v0 + buy
    r = (v_end + sell + div - v0 - buy) / denom if denom > 0 else 0.0
    nav = prev["nav"] * (1 + r)
    st["hist"].append({"date": today, "nav": round(nav, 2), "bench": round(1000 * kp[today] / st["kospi0"], 2), "kospi": kp[today],
                       "net": round(v_end), "buy": round(buy), "sell": round(sell), "div": round(div), "r": round(r * 100, 3),
                       "n": len(hold), "fills": len(fl)})
    st["holdings"], st["cut"], st["updated"] = hold, now.isoformat(), now.strftime("%Y-%m-%d %H:%M")
    st["trades"] = st["trades"][-300:]
    save(st)
    return st["hist"][-1]


def summary(viewer: bool = False) -> dict:
    st = load()
    if not st.get("hist"):
        return {"empty": True, "note": "아직 설정 전 — 평일 장 마감 후 16:10에 처음 설정돼요 (바로 하려면 서버에서 python chartpage/my_fund.py run)"}
    last = st["hist"][-1]
    net = last["net"] or 0
    hold = []
    for c, h in sorted(st["holdings"].items(), key=lambda kv: -kv[1]["val"]):
        hold.append({"code": c, "name": h["name"], "us": h.get("us"), "qty": h["qty"], "price": h["px"],
                     "weight": round(h["val"] / net * 100, 1) if net else None,
                     "pnl": round((h["px"] / h["avg"] - 1) * 100, 2) if h.get("avg") else None})
    out = {"inception": st["inception"], "updated": st.get("updated"), "last": last,
           "ret": round((last["nav"] / 1000 - 1) * 100, 2), "bench_ret": round((last["bench"] / 1000 - 1) * 100, 2),
           "hist": [{"d": r["date"], "nav": r["nav"], "bench": r["bench"]} for r in st["hist"]],
           "holdings": hold, "trades": st["trades"][-30:][::-1], "divs": st.get("divs", [])[-10:][::-1]}
    if viewer:                                                # 보기 전용: 금액·주수 숨김, 기준가·비중·수익률만
        out["last"] = {k: v for k, v in last.items() if k in ("date", "nav", "bench", "r", "n")}
        for h in out["holdings"]:
            h.pop("qty", None)
        out["trades"] = [{k: v for k, v in t.items() if k in ("date", "code", "name", "side", "price", "us")} for t in out["trades"]]
        out["divs"] = []
        out["hidden"] = True
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "show"
    if cmd == "run":
        print(json.dumps(run(sys.argv[2] if len(sys.argv) > 2 else None), ensure_ascii=False, indent=1))
    elif cmd == "reset":
        if os.path.exists(PATH):
            os.replace(PATH, PATH + f".bak{int(time.time())}")
        print("초기화 — 다음 run 때 새로 설정")
    else:
        print(json.dumps(summary(), ensure_ascii=False, indent=1)[:3000])
