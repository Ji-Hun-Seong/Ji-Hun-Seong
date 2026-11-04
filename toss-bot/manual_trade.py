"""manual_trade.py — 대시보드에서 직접 사고파는 수동 주문 (토스증권 Open API)

안전장치 (철칙 1: 절대 대출해서 투자하지 않는다 · 철칙 2: FOMO 금지)
  - 주인(owner)만: 보기 전용(아빠)은 서버에서 막음 (dashboard.do_POST)
  - 현금 매수 가능 금액(cashBuyingPower, 미수 없이 순수 현금) 안에서만 — 신용·미수 주문은 아예 만들지 않음
  - 1회 주문 한도: MANUAL_MAX_ORDER_KRW (기본 300만원) · MANUAL_MAX_ORDER_USD (기본 2,000달러)
  - 오늘 +10%↑(시총 5조↑ 대형주는 +5%↑) 오른 종목을 살 때는 '왜 사는지' 한 줄을 적어야 주문됨
  - 긴급 정지(STOP)가 켜져 있으면 새 매수는 막고 매도·취소만 허용
  - 모든 주문·취소는 state/manual_orders.jsonl 에 기록(이유 포함) — 나중에 매매일지로
  - 멱등키(clientOrderId)로 같은 주문이 두 번 나가지 않게, 1억원↑ 주문은 거부
봇(bot.py)은 자기 장부 종목만 관리하므로 여기서 산 종목을 봇이 팔지 않음.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid

import bot

LOG = os.path.join(bot.STATE_DIR, "manual_orders.jsonl")
MAX_KRW = float(os.environ.get("MANUAL_MAX_ORDER_KRW") or 3_000_000)
MAX_USD = float(os.environ.get("MANUAL_MAX_ORDER_USD") or 2000)
FOMO_PCT, FOMO_PCT_BIG = 10.0, 5.0

_api, _lock = None, threading.Lock()
_limits = {}


def api():
    global _api
    with _lock:
        if _api is None:
            _api = bot.api()
        return _api


def enabled() -> tuple[bool, str]:
    if not (os.environ.get("TOSS_CLIENT_ID") and os.environ.get("TOSS_CLIENT_SECRET")):
        return False, "서버 .env 에 토스 Open API 키가 없음"
    if os.environ.get("MANUAL_TRADING", "1") == "0":
        return False, "MANUAL_TRADING=0 (서버 설정에서 수동 주문 꺼짐)"
    return True, ""


def is_us(code: str) -> bool:
    return not code.isdigit()


def tick_kr(p: float) -> int:
    """국내 호가 단위 (2023년 개편 — 코스피·코스닥 공통)"""
    return 1 if p < 2000 else 5 if p < 5000 else 10 if p < 20000 else 50 if p < 50000 else 100 if p < 200000 else 500 if p < 500000 else 1000


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def norm_ob(ob: dict) -> dict:
    """토스 호가(REST·웹소켓 같은 모양) → 매도·매수 모두 비싼 가격부터, 잔량 합계"""
    asks = sorted([{"p": _f(x.get("price")), "v": _f(x.get("volume"))} for x in ob.get("asks") or [] if _f(x.get("price"))], key=lambda x: -x["p"])
    bids = sorted([{"p": _f(x.get("price")), "v": _f(x.get("volume"))} for x in ob.get("bids") or [] if _f(x.get("price"))], key=lambda x: -x["p"])
    return {"ts": ob.get("timestamp"), "ccy": ob.get("currency"), "asks": asks, "bids": bids,
            "sum_ask": sum(x["v"] or 0 for x in asks), "sum_bid": sum(x["v"] or 0 for x in bids)}


def limits(code: str):
    hit = _limits.get(code)
    if not hit or time.time() - hit[0] > 300:              # 상·하한가는 하루 고정 → 5분 캐시
        try:
            lim = api().price_limits(code) or {}
            hit = (time.time(), _f(lim.get("upperLimitPrice")), _f(lim.get("lowerLimitPrice")))
            _limits[code] = hit
        except Exception:
            hit = (0, None, None)
    return hit[1], hit[2]


def orderbook(code: str) -> dict:
    """호가창 — 매도(위, 비싼 가격부터) / 매수(아래, 비싼 가격부터) + 상·하한가 + 현재가"""
    a = api()
    out = {"code": code, **norm_ob(a.orderbook(code) or {})}
    out["ccy"] = out["ccy"] or ("USD" if is_us(code) else "KRW")
    try:
        lp = (a.prices([code]) or [{}])[0]
        out["last"] = _f(lp.get("lastPrice"))
    except Exception:
        out["last"] = None
    out["upper"], out["lower"] = limits(code)
    return out


def _prev_close(code: str):
    """전일 종가 — 오늘 봉이 있으면 그 앞, 없으면(장 전) 마지막 봉"""
    try:
        rows = bot.daily(api(), code, 3)
        if not rows:
            return None
        today = bot.now().strftime("%Y-%m-%d") if not is_us(code) else None
        if today and rows[-1][0] == today:
            return rows[-2][4] if len(rows) >= 2 else None
        return rows[-1][4] if not is_us(code) else (rows[-2][4] if len(rows) >= 2 else None)
    except Exception:
        return None


def info(code: str) -> dict:
    """주문 화면용 — 현금 매수 가능 금액·팔 수 있는 수량·내 보유·이 종목 미체결·한도"""
    a = api()
    us = is_us(code)
    out = {"code": code, "us": us, "ccy": "USD" if us else "KRW", "max_order": MAX_USD if us else MAX_KRW,
           "stopped": bot.stopped(), "fomo_pct": FOMO_PCT, "fomo_pct_big": FOMO_PCT_BIG}
    try:
        out["cash"] = a.buying_power_usd() if us else a.buying_power()
    except Exception as e:
        out["cash"], out["cash_err"] = None, str(e)[:120]
    try:
        out["sellable"] = float(a.req("GET", "/api/v1/sellable-quantity", "ORDER_INFO", {"symbol": code}, account=True)["sellableQuantity"])
    except Exception:
        out["sellable"] = 0
    try:
        it = next((x for x in (a.holdings() or {}).get("items", []) if x.get("symbol") == code), None)
        out["hold"] = {"qty": _f(it.get("quantity")), "avg": _f(it.get("averagePurchasePrice")), "last": _f(it.get("lastPrice"))} if it else None
    except Exception:
        out["hold"] = None
    try:
        out["open"] = [_order_row(o) for o in a.open_orders(code)]
    except Exception as e:
        out["open"], out["open_err"] = [], str(e)[:120]
    pc = _prev_close(code)
    out["prev_close"] = pc
    return out


def _order_row(o: dict) -> dict:
    ex = o.get("execution") or {}
    return {"id": o.get("orderId"), "side": o.get("side"), "type": o.get("orderType"), "status": o.get("status"),
            "price": _f(o.get("price")), "qty": _f(o.get("quantity")), "filled": _f(ex.get("filledQuantity")) or 0,
            "avg": _f(ex.get("averagePrice") or ex.get("executionAveragePrice")), "at": o.get("orderedAt")}


def _log(rec: dict):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({"t": time.strftime("%Y-%m-%d %H:%M:%S"), **rec}, ensure_ascii=False) + "\n")


class Reject(Exception):
    """주문 전에 막힘 — 사용자에게 그대로 보여 줄 문장"""


def place(req: dict, mcap_eok: float | None = None) -> dict:
    """req = {code, side BUY|SELL, type LIMIT|MARKET, qty, price?, reason?, confirm: true, cid}"""
    ok, why = enabled()
    if not ok:
        raise Reject(why)
    code = str(req.get("code") or "").strip().upper()
    side = req.get("side")
    otype = req.get("type") or "LIMIT"
    if not code or side not in ("BUY", "SELL") or otype not in ("LIMIT", "MARKET"):
        raise Reject("주문 정보가 올바르지 않습니다")
    if req.get("confirm") is not True:
        raise Reject("확인 단계를 거치지 않은 주문")
    us = is_us(code)
    qty = _f(req.get("qty"))
    if not qty or qty <= 0 or (not us and qty != int(qty)):
        raise Reject("수량을 확인하세요 (국내는 1주 단위)")
    price = _f(req.get("price")) if otype == "LIMIT" else None
    if otype == "LIMIT" and (not price or price <= 0):
        raise Reject("지정가를 입력하세요")
    if not us and price and price % tick_kr(price):
        raise Reject(f"호가 단위가 맞지 않음 — {tick_kr(price):,}원 단위로")
    a = api()
    ob = orderbook(code)
    ref = price or (ob["asks"][-1]["p"] if side == "BUY" and ob["asks"] else ob["bids"][0]["p"] if ob["bids"] else ob.get("last"))
    if not ref:
        raise Reject("현재 호가를 받지 못해 주문하지 않았습니다")
    if otype == "LIMIT" and ob.get("upper") and ob.get("lower") and not (ob["lower"] <= price <= ob["upper"]):
        raise Reject(f"가격이 상·하한가({ob['lower']:,.0f}~{ob['upper']:,.0f}) 밖입니다")
    est = qty * ref * (1.02 if otype == "MARKET" else 1.0)          # 시장가는 2% 여유를 두고 계산
    cap = MAX_USD if us else MAX_KRW
    if side == "BUY":
        if bot.stopped():
            raise Reject("⛔ 긴급 정지가 켜져 있어 새 매수는 막혀 있어요 (매도·취소는 가능)")
        cash = a.buying_power_usd() if us else a.buying_power()
        if est > cash:
            raise Reject(f"현금 매수 가능 금액({cash:,.0f}) 초과 — 🚫 철칙 1: 빚(미수·신용)으로는 사지 않아요")
        if est > cap:
            raise Reject(f"1회 주문 한도({cap:,.0f}) 초과 — 서버 .env 의 MANUAL_MAX_ORDER_{'USD' if us else 'KRW'} 로 바꿀 수 있어요")
        pc = _prev_close(code)
        cur = ob.get("last") or ref
        chg = (cur / pc - 1) * 100 if pc else None
        lim = FOMO_PCT_BIG if (mcap_eok or 0) >= 50000 else FOMO_PCT
        if chg is not None and chg >= lim and len((req.get("reason") or "").strip()) < 8:
            raise Reject(f"🧘 오늘 {chg:+.1f}% 오른 종목이에요 (FOMO 기준 +{lim:.0f}%) — 왜 사는지 한 줄(8자 이상)을 적어야 주문돼요")
    else:
        sellable = float(a.req("GET", "/api/v1/sellable-quantity", "ORDER_INFO", {"symbol": code}, account=True)["sellableQuantity"])
        if qty > sellable:
            raise Reject(f"팔 수 있는 수량({sellable:g}주)보다 많아요")
    if not us and est >= 1e8:
        raise Reject("1억원 이상 주문은 앱에서 직접 하세요")
    cid = str(req.get("cid") or "")
    if not cid or len(cid) > 36 or not all(c.isalnum() or c in "-_" for c in cid):
        cid = "m-" + uuid.uuid4().hex[:30]
    rec = {"code": code, "side": side, "type": otype, "qty": qty, "price": price, "est": round(est, 2), "reason": (req.get("reason") or "").strip()[:300], "cid": cid}
    try:
        r = a.order(code, side, int(qty) if not us else qty, cid, order_type=otype, tif="DAY", price=(int(price) if price and not us else price))
    except Exception as e:
        _log({**rec, "ok": False, "error": str(e)[:300]})
        raise
    _log({**rec, "ok": True, "order_id": (r or {}).get("orderId")})
    return {"ok": True, "order_id": (r or {}).get("orderId"), "est": est}


def cancel(order_id: str) -> dict:
    ok, why = enabled()
    if not ok:
        raise Reject(why)
    if not order_id or len(order_id) > 128:
        raise Reject("주문번호가 올바르지 않습니다")
    r = api().cancel(order_id)
    _log({"cancel": order_id, "ok": True})
    return {"ok": True, "order_id": (r or {}).get("orderId") or order_id}
