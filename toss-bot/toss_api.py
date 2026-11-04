"""토스증권 Open API 클라이언트 (REST, v1.2.x 기준)
- 토큰: client 당 1개만 유효 → 파일 캐시로 재사용 (재발급하면 이전 토큰 즉시 무효)
- 허용 IP 에서만 호출 가능 (WTS 설정 > Open API > 허용 IP 관리)
"""
import fcntl, json, os, time, threading
import requests

BASE = "https://openapi.tossinvest.com"
# API 그룹별 초당 한도(공식 문서) — 여유 있게 80%만 사용
TPS = {"AUTH": 5, "ACCOUNT": 1, "ASSET": 5, "STOCK": 5, "STOCK_ALL": 1, "MARKET_INFO": 3, "MARKET_DATA": 15,
       "MARKET_DATA_CHART": 20, "RANKING": 5, "MARKET_INDICATOR_CHART": 5, "ORDER": 10, "ORDER_HISTORY": 5,
       "ORDER_INFO": 3, "CONDITIONAL_ORDER": 5, "CONDITIONAL_ORDER_HISTORY": 10}


class TossError(Exception):
    def __init__(self, status, code, message, request_id=None):
        super().__init__(f"{status} {code}: {message} (requestId={request_id})")
        self.status, self.code, self.request_id = status, code, request_id


class Toss:
    def __init__(self, client_id, client_secret, token_file, account_seq=None):
        self.cid, self.secret, self.token_file = client_id, client_secret, token_file
        self.account = account_seq
        self.s = requests.Session()
        self._last = {}
        self._lock = threading.Lock()

    # ── 공통 ──
    def _throttle(self, group):
        gap = 1.0 / (TPS.get(group, 3) * 0.8)
        with self._lock:
            wait = self._last.get(group, 0) + gap - time.time()
            if wait > 0:
                time.sleep(wait)
            self._last[group] = time.time()

    def _cached_token(self):
        try:
            t = json.load(open(self.token_file))
            return t["access_token"] if t.get("exp", 0) > time.time() + 300 else None
        except Exception:
            return None

    def token(self, force=False):
        if not force:
            t = self._cached_token()
            if t:
                return t
        # 봇·대시보드 두 프로세스가 같은 토큰을 씀 → 발급은 한 곳에서만 (재발급하면 이전 토큰이 바로 무효라서)
        with open(self.token_file + ".lock", "w") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            if not force or (os.path.exists(self.token_file) and time.time() - os.path.getmtime(self.token_file) < 10):
                t = self._cached_token()
                if t:
                    return t
            return self._issue()

    def _issue(self):
        self._throttle("AUTH")
        r = self.s.post(f"{BASE}/oauth2/token", timeout=20,
                        data={"grant_type": "client_credentials", "client_id": self.cid, "client_secret": self.secret})
        if r.status_code != 200:
            try:
                j = r.json()
            except Exception:
                j = {}
            hint = " — 허용 IP 미등록일 수 있음" if r.status_code == 403 else ""
            raise TossError(r.status_code, j.get("error", "auth"), (j.get("error_description") or r.text[:200]) + hint)
        j = r.json()
        tmp = self.token_file + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"access_token": j["access_token"], "exp": time.time() + int(j.get("expires_in", 3600))}, f)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.token_file)
        return j["access_token"]

    def req(self, method, path, group, params=None, body=None, account=False, retry=3):
        for i in range(retry):
            self._throttle(group)
            h = {"Authorization": f"Bearer {self.token()}", "Accept": "application/json"}
            if account:
                h["X-Tossinvest-Account"] = str(self.account)
            try:
                r = self.s.request(method, BASE + path, params=params, json=body, headers=h, timeout=20)
            except requests.RequestException as e:
                if method != "GET" and body is not None and not (body or {}).get("clientOrderId"):
                    raise                                   # 멱등키 없는 주문은 재시도 안 함
                if i == retry - 1:
                    raise
                time.sleep(2 * (i + 1)); continue
            if r.status_code == 200:
                return r.json().get("result")
            try:
                err = r.json().get("error") or {}
            except Exception:
                err = {}
            code = err.get("code", "") if isinstance(err, dict) else str(err)
            if r.status_code == 401 or code in ("invalid-token", "expired-token"):
                self.token(force=True); continue
            if r.status_code == 429 or r.status_code >= 500:
                if i < retry - 1:
                    time.sleep(1.5 * (i + 1)); continue
            msg = err.get("message", r.text[:200]) if isinstance(err, dict) else r.text[:200]
            if r.status_code == 403:
                msg += " — 서버 IP가 토스 허용 IP에 등록됐는지 확인"
            raise TossError(r.status_code, code, msg, err.get("requestId") if isinstance(err, dict) else None)
        raise TossError(0, "retry-exhausted", path)

    # ── 시세·종목 ──
    def candles(self, symbol, count=200, before=None):
        p = {"symbol": symbol, "interval": "1d", "count": count, "adjusted": "true"}
        if before:
            p["before"] = before
        return self.req("GET", "/api/v1/candles", "MARKET_DATA_CHART", p)

    def index_candles(self, symbol="KOSPI", count=200, before=None):
        p = {"interval": "1d", "count": count}
        if before:
            p["before"] = before
        return self.req("GET", f"/api/v1/market-indicators/{symbol}/candles", "MARKET_INDICATOR_CHART", p)

    def stocks_all(self, market="KOSPI"):
        return self.req("GET", "/api/v1/stocks/all", "STOCK_ALL",
                        {"market": market, "status": "ACTIVE", "securityType": "STOCK", "commonShare": "true"})

    def orderbook(self, symbol):
        """호가 — {timestamp, currency, asks:[{price, volume}], bids:[...]} (asks 는 위쪽=비싼 가격부터)"""
        return self.req("GET", "/api/v1/orderbook", "MARKET_DATA", {"symbol": symbol})

    def price_limits(self, symbol):
        return self.req("GET", "/api/v1/price-limits", "MARKET_DATA", {"symbol": symbol})

    def trades(self, symbol, count=50):
        return self.req("GET", "/api/v1/trades", "MARKET_DATA", {"symbol": symbol, "count": count}) or []

    def prices(self, symbols):
        out = []
        for i in range(0, len(symbols), 200):
            out += self.req("GET", "/api/v1/prices", "MARKET_DATA", {"symbols": ",".join(symbols[i:i + 200])}) or []
        return out

    def stock_info(self, symbols):
        return self.req("GET", "/api/v1/stocks", "STOCK", {"symbols": ",".join(symbols)}) or []

    def us_calendar(self, date=None):
        return self.req("GET", "/api/v1/market-calendar/US", "MARKET_INFO", {"date": date} if date else None)

    def warnings(self, symbol):
        return self.req("GET", f"/api/v1/stocks/{symbol}/warnings", "STOCK")

    def calendar(self, date=None):
        return self.req("GET", "/api/v1/market-calendar/KR", "MARKET_INFO", {"date": date} if date else None)

    # ── 계좌 ──
    def accounts(self):
        return self.req("GET", "/api/v1/accounts", "ACCOUNT")

    def holdings(self):
        return self.req("GET", "/api/v1/holdings", "ASSET", account=True)

    def buying_power(self):
        return float(self.req("GET", "/api/v1/buying-power", "ORDER_INFO", {"currency": "KRW"}, account=True)["cashBuyingPower"])

    def sellable(self, symbol):
        return int(float(self.req("GET", "/api/v1/sellable-quantity", "ORDER_INFO", {"symbol": symbol}, account=True)["sellableQuantity"]))

    # ── 주문 ──
    def order(self, symbol, side, qty=None, client_order_id=None, order_type="MARKET", tif="DAY", price=None, amount=None):
        body = {"clientOrderId": client_order_id, "symbol": symbol, "side": side, "orderType": order_type}
        if tif:
            body["timeInForce"] = tif
        if amount is not None:
            body["orderAmount"] = f"{amount:.2f}"          # 미국 시장가 금액 주문(정규장)
        else:
            body["quantity"] = str(qty)
        if order_type == "LIMIT":
            body["price"] = str(price)
        return self.req("POST", "/api/v1/orders", "ORDER", body=body, account=True)

    def buying_power_usd(self):
        return float(self.req("GET", "/api/v1/buying-power", "ORDER_INFO", {"currency": "USD"}, account=True)["cashBuyingPower"])

    def get_order(self, order_id):
        return self.req("GET", f"/api/v1/orders/{order_id}", "ORDER_HISTORY", account=True)

    def open_orders(self, symbol=None):
        p = {"status": "OPEN", "limit": 100}
        if symbol:
            p["symbol"] = symbol
        return (self.req("GET", "/api/v1/orders", "ORDER_HISTORY", p, account=True) or {}).get("orders", [])

    def modify(self, order_id, price=None, qty=None, order_type="LIMIT"):
        body = {"orderType": order_type}
        if price is not None:
            body["price"] = str(price)
        if qty is not None:
            body["quantity"] = str(qty)
        return self.req("POST", f"/api/v1/orders/{order_id}/modify", "ORDER", body=body, account=True)

    def cancel(self, order_id):
        return self.req("POST", f"/api/v1/orders/{order_id}/cancel", "ORDER", body={}, account=True)

    def orders(self, status="CLOSED", symbol=None, date_from=None, date_to=None, limit=100, cursor=None):
        p = {"status": status, "limit": limit}
        for k, v in (("symbol", symbol), ("from", date_from), ("to", date_to), ("cursor", cursor)):
            if v:
                p[k] = v
        return self.req("GET", "/api/v1/orders", "ORDER_HISTORY", p, account=True) or {}

    def conditional_orders(self, status="OPEN", symbol=None):
        p = {"status": status, "limit": 100}
        if symbol:
            p["symbol"] = symbol
        return (self.req("GET", "/api/v1/conditional-orders", "CONDITIONAL_ORDER_HISTORY", p, account=True) or {}).get("conditionalOrders", [])

    def cancel_conditional(self, cid):
        return self.req("DELETE", f"/api/v1/conditional-orders/{cid}", "CONDITIONAL_ORDER", account=True)
