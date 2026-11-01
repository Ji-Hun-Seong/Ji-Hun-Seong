"""토스증권 스윙 자동매매 봇 (코스피, 일봉)

사용법 (서버에서, .env 설정 후):
  python bot.py test        # API 연결·계좌·허용 IP 점검 (주문 없음)
  python bot.py evening     # 장 마감 후: 일봉 갱신 → 신호 계산 → 내일 주문 계획 저장 → 텔레그램 보고
  python bot.py open        # 08:45: 계획대로 시가(장 시작 동시호가) 주문. 가상 모드면 기록만
  python bot.py confirm     # 09:10: 체결 확인 → 장부 반영 → 텔레그램 보고
  python bot.py status      # 장부·성과 출력
  python bot.py mode live|paper   # 모드 전환 (live는 확인 문구 필요)
  touch STOP                # 이 파일이 있으면 새 주문을 전혀 내지 않음 (긴급 정지)

안전장치
  - 봇 장부에 있는 종목·수량만 매도 (계좌의 다른 보유 주식은 절대 건드리지 않음)
  - 봇 운용 한도(BOT_CAPITAL), 1회 주문 한도(MAX_ORDER_KRW), 하루 신규 매수 수(MAX_NEW_BUYS) 제한
  - 투자경고·위험·과열·정리매매 종목 매수 제외
  - 주문마다 clientOrderId(멱등키) → 재시도해도 중복 주문 없음
  - 같은 작업이 동시에 두 번 실행되지 않도록 잠금
"""
import datetime as dt, fcntl, json, math, os, sys, time, traceback
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from toss_api import Toss, TossError
import market_data, strategy

KST = dt.timezone(dt.timedelta(hours=9))
BUY_COST, SELL_COST = 0.00015 + 0.001, 0.00015 + 0.0020 + 0.001     # 백테스트와 같은 비용 가정(수수료+세금+슬리피지)


def load_env():
    p = os.path.join(HERE, ".env")
    if os.path.exists(p):
        for line in open(p):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                v = v.split(" #")[0].strip().strip('"').strip("'")      # 줄 끝 주석 제거
                os.environ.setdefault(k.strip(), v)


load_env()
CFG = dict(
    capital=float(os.environ.get("BOT_CAPITAL", "1000000")),        # 봇이 굴리는 총액(원)
    max_order=float(os.environ.get("MAX_ORDER_KRW", "200000")),     # 종목당 1회 최대 매수액
    max_new=int(os.environ.get("MAX_NEW_BUYS", "3")),               # 하루 신규 매수 최대 종목 수
    max_pos=int(os.environ.get("MAX_POSITIONS", str(strategy.P["MAX_POS"]))),
)
STATE = os.path.join(HERE, "state", "ledger.json")
DB = os.path.join(HERE, "state", "candles.sqlite")
LOG = os.path.join(HERE, "state", "bot.log")
os.makedirs(os.path.join(HERE, "state"), exist_ok=True)


def now():
    return dt.datetime.now(KST)


def log(*a):
    msg = now().strftime("%m-%d %H:%M:%S ") + " ".join(str(x) for x in a)
    print(msg, flush=True)
    with open(LOG, "a") as f:
        f.write(msg + "\n")


def tg(text):
    tok, chat = os.environ.get("TG_TOKEN"), os.environ.get("TG_CHAT_ID")
    if not tok or not chat:
        log("[텔레그램 미설정]", text[:200]); return
    for i in range(3):
        try:
            r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                              json={"chat_id": chat, "text": text[:4000], "parse_mode": "HTML",
                                    "disable_web_page_preview": True}, timeout=20)
            if r.ok:
                return
            log("텔레그램 실패", r.status_code, r.text[:200])
        except Exception as e:
            log("텔레그램 예외", e)
        time.sleep(3)


def load_state():
    if os.path.exists(STATE):
        return json.load(open(STATE))
    return {"mode": "paper", "created": now().date().isoformat(), "cash": CFG["capital"], "positions": {},
            "plan": None, "orders": {}, "closed": [], "equity": []}


def save_state(s):
    tmp = STATE + ".tmp"
    json.dump(s, open(tmp, "w"), ensure_ascii=False, indent=1)
    os.replace(tmp, STATE)


def api():
    a = Toss(os.environ["TOSS_CLIENT_ID"], os.environ["TOSS_CLIENT_SECRET"], os.path.join(HERE, "state", "token.json"),
             os.environ.get("TOSS_ACCOUNT_SEQ"))
    if not a.account:
        accs = a.accounts() or []
        if not accs:
            raise RuntimeError("종합매매 계좌가 없습니다")
        a.account = accs[0]["accountSeq"]
    return a


def trading_day(a, d=None):
    cal = a.calendar(d)
    t = cal["today"]
    return t.get("integrated") is not None and (t["integrated"] or {}).get("regularMarket") is not None, cal


def won(x):
    return f"{x:,.0f}원"


def equity(s, prices):
    return s["cash"] + sum(p["qty"] * prices.get(sym, p["last"]) for sym, p in s["positions"].items())


# ── 장 마감 후 ──────────────────────────────────────
def evening(a, s):
    is_td, cal = trading_day(a)
    if not is_td:
        log("휴장일 → 건너뜀"); return
    store = market_data.Store(DB)
    n, fail = market_data.refresh(a, store, log)
    log(f"일봉 갱신 {n}종목, 실패 {len(fail)}")
    if n < 500:
        tg(f"⚠️ 토스봇: 일봉 갱신 실패가 많음 ({n}종목 성공, {len(fail)} 실패) → 오늘은 신호 계산 안 함\n{fail[:3]}"); return
    panel = store.panel()
    last = panel["c"].index[-1].date()
    if last != now().date():
        tg(f"⚠️ 토스봇: 오늘 일봉이 아직 없음(마지막 {last}) → 신호 계산 안 함"); return
    f = strategy.compute(panel)
    sig = strategy.today_signals(f, s["positions"])
    names = store.names()
    for sym, p in s["positions"].items():               # 장부 종가 갱신
        c = f["C"][sym].iloc[-1] if sym in f["C"] else None
        if c == c and c:
            p["last"] = float(c)
    # 내일 주문 계획
    sells = [{"symbol": sym, "qty": s["positions"][sym]["qty"], "why": why} for sym, why in sig["sells"]]
    free = CFG["max_pos"] - (len(s["positions"]) - len(sells))
    eq = equity(s, {})
    slot = min(eq / CFG["max_pos"], CFG["max_order"])
    buys, skipped = [], []
    for b in sig["buys"]:
        if len(buys) >= min(free, CFG["max_new"]):
            break
        try:
            w = [x["warningType"] for x in (a.warnings(b["symbol"]) or [])
                 if x["warningType"] in ("LIQUIDATION_TRADING", "OVERHEATED", "INVESTMENT_WARNING", "INVESTMENT_RISK")]
        except Exception as e:
            w = [f"조회실패:{e}"]
        if w:
            skipped.append(f"{names.get(b['symbol'], b['symbol'])}({','.join(w)})"); continue
        qty = math.floor(slot / (b["close"] * 1.05))       # 시가 갭상승 5%까지 감안
        if qty < 1:
            skipped.append(f"{names.get(b['symbol'], b['symbol'])}(1주 가격 {won(b['close'])} > 한도)"); continue
        buys.append({**b, "qty": qty, "name": names.get(b["symbol"], b["symbol"])})
    nb = cal["nextBusinessDay"]["date"]
    s["plan"] = {"for": nb, "made": sig["date"], "sells": sells, "buys": buys}
    s["equity"].append([sig["date"], round(eq)])
    save_state(s)

    mode = "🧪 가상" if s["mode"] == "paper" else "💰 실전"
    L = [f"📈 <b>토스봇 장 마감 보고</b> {sig['date']} [{mode}]",
         f"시장: KOSPI {sig['idx']:,.0f} / 200일선 {sig['idx_ma200']:,.0f} → {'🟢 매수 허용' if sig['regime'] else '🔴 신규 매수 중지'}",
         f"평가 {won(eq)} (원금 {won(CFG['capital'])}, {eq / CFG['capital'] - 1:+.1%}) · 현금 {won(s['cash'])}", ""]
    if s["positions"]:
        L.append("<b>보유</b>")
        for sym, p in s["positions"].items():
            r = f["rsi"][sym].iloc[-1] if sym in f["rsi"] else float("nan")
            L.append(f"▪ {p['name']} {p['qty']}주 {p['last'] / p['entry'] - 1:+.1%} (RSI {r:.0f}{', 손절 ' + won(p['stop']) if p.get('stop') else ''}, 매도 기준 RSI&lt;{strategy.P['RSI_OUT']})")
        L.append("")
    L.append(f"<b>내일({nb}) 시가 주문 계획</b>")
    for x in sells:
        L.append(f"🔻 매도 {s['positions'][x['symbol']]['name']} {x['qty']}주 — {x['why']}")
    for b in buys:
        L.append(f"🔺 매수 {b['name']} {b['qty']}주 (종가 {won(b['close'])}, RSI {b['rsi']:.0f}, 거래량 {b['vr']:.1f}배, "
                 f"60일 고점 {won(b['fib_hi'])} 돌파 · 피보 61.8% {won(b['fib_hi'] - (b['fib_hi'] - b['fib_lo']) * 0.618)})")
    if not sells and not buys:
        L.append("없음")
    if skipped:
        L.append("제외: " + ", ".join(skipped[:8]))
    more = len(sig["buys"]) - len(buys) - len(skipped)
    if more > 0:
        L.append(f"(신호 {len(sig['buys'])}개 중 자리·한도 때문에 {more}개 대기)")
    if s["mode"] == "paper" and (dt.date.fromisoformat(sig["date"]) - dt.date.fromisoformat(s["created"])).days >= 14:
        cl = s["closed"]
        L += ["", f"🧪 가상 운용 {(dt.date.fromisoformat(sig['date']) - dt.date.fromisoformat(s['created'])).days}일째: "
              f"평가 {eq / CFG['capital'] - 1:+.1%}, 청산 {len(cl)}건"
              + (f" (승률 {sum(1 for x in cl if x['ret'] > 0) / len(cl):.0%})" if cl else "")
              + " → 실전 전환은 서버에서 <code>python bot.py mode live</code>"]
    tg("\n".join(L))


# ── 장 시작 주문 ─────────────────────────────────────
def place_open(a, s):
    plan = s.get("plan")
    today = now().date().isoformat()
    if not plan or plan["for"] != today:
        log("오늘 계획 없음"); return
    if os.path.exists(os.path.join(HERE, "STOP")):
        tg("⛔ STOP 파일이 있어 오늘 주문을 내지 않았습니다"); return
    if plan.get("placed"):
        log("이미 주문함"); return
    orders = []
    if s["mode"] == "live":
        cash = a.buying_power()
        for x in plan["sells"]:
            sym = x["symbol"]
            if sym not in s["positions"]:
                continue
            q = min(s["positions"][sym]["qty"], a.sellable(sym))  # 장부 수량 이상은 절대 안 팜
            if q <= 0:
                continue
            cid = f"{today}-S-{sym}"
            r = a.order(sym, "SELL", q, cid)
            orders.append({"id": r["orderId"], "cid": cid, "symbol": sym, "side": "SELL", "qty": q})
            log("매도 주문", sym, q, r)
        budget_left = min(cash, CFG["capital"] - sum(p["qty"] * p["entry"] for p in s["positions"].values()))
        for b in plan["buys"]:
            px = a.prices([b["symbol"]])
            ref = float(px[0]["lastPrice"]) if px else b["close"]
            q = min(b["qty"], math.floor(min(budget_left, CFG["max_order"]) / (ref * 1.05)))
            if q < 1:
                log("예산 부족으로 매수 건너뜀", b["symbol"]); continue
            cid = f"{today}-B-{b['symbol']}"
            r = a.order(b["symbol"], "BUY", q, cid)
            budget_left -= q * ref * 1.05
            orders.append({"id": r["orderId"], "cid": cid, "symbol": b["symbol"], "side": "BUY", "qty": q,
                           "name": b["name"], "stop": b["stop"]})
            log("매수 주문", b["symbol"], q, r)
    else:
        for x in plan["sells"]:
            orders.append({"id": None, "symbol": x["symbol"], "side": "SELL", "qty": x["qty"]})
        for b in plan["buys"]:
            orders.append({"id": None, "symbol": b["symbol"], "side": "BUY", "qty": b["qty"], "name": b["name"], "stop": b["stop"]})
    plan["placed"], plan["orders"] = now().isoformat(timespec="seconds"), orders
    save_state(s)
    if orders:
        tg(("💰" if s["mode"] == "live" else "🧪") + f" 토스봇 시가 주문 {len(orders)}건 접수 "
           + ("(실제 주문)" if s["mode"] == "live" else "(가상 — 실제 주문 없음)"))


# ── 체결 확인 ────────────────────────────────────────
def confirm(a, s):
    plan = s.get("plan")
    today = now().date().isoformat()
    if not plan or plan["for"] != today or not plan.get("placed") or plan.get("confirmed"):
        log("확인할 주문 없음"); return
    L = [f"✅ <b>토스봇 체결</b> {today} [{'💰 실전' if s['mode'] == 'live' else '🧪 가상'}]"]
    for o in plan["orders"]:
        sym = o["symbol"]
        if s["mode"] == "live":
            d = a.get_order(o["id"])
            ex = d["execution"]
            q = int(float(ex["filledQuantity"] or 0))
            px = float(ex["averageFilledPrice"]) if ex.get("averageFilledPrice") else None
            fee = float(ex.get("commission") or 0) + float(ex.get("tax") or 0)
            if d["status"] in ("PENDING", "PARTIAL_FILLED"):
                try:
                    a.cancel(o["id"])
                except TossError as e:
                    log("취소 실패", e)
        else:
            c = a.candles(sym, count=1).get("candles", [])
            if not c or c[0]["timestamp"][:10] != today:
                L.append(f"⚠️ {sym} 오늘 시가 없음(거래정지?) → 가상 체결 안 함"); continue
            px, q = float(c[0]["openPrice"]), o["qty"]
            fee = px * q * (BUY_COST if o["side"] == "BUY" else SELL_COST)
        if not q or not px:
            L.append(f"⚠️ {o.get('name', sym)} {o['side']} 미체결"); continue
        if o["side"] == "BUY":
            cost = px * q + fee
            s["cash"] -= cost
            s["positions"][sym] = {"name": o.get("name", sym), "qty": q, "entry": px, "last": px, "cost": cost,
                                   "date": today, "stop": o.get("stop")}
            L.append(f"🔺 {o.get('name', sym)} {q}주 @ {won(px)}")
        else:
            p = s["positions"].get(sym)
            if not p:
                continue
            q = min(q, p["qty"])
            proceeds = px * q - fee
            s["cash"] += proceeds
            ret = proceeds / (p["cost"] * q / p["qty"]) - 1
            s["closed"].append({"symbol": sym, "name": p["name"], "in": p["date"], "out": today, "ret": round(ret, 4),
                                "pnl": round(proceeds - p["cost"] * q / p["qty"])})
            L.append(f"🔻 {p['name']} {q}주 @ {won(px)} → {ret:+.1%} ({won(proceeds - p['cost'] * q / p['qty'])})")
            if q >= p["qty"]:
                del s["positions"][sym]
            else:
                p["cost"] *= (p["qty"] - q) / p["qty"]; p["qty"] -= q
    plan["confirmed"] = now().isoformat(timespec="seconds")
    save_state(s)
    if len(L) > 1:
        tg("\n".join(L))


def status(s):
    print(json.dumps({k: s[k] for k in ("mode", "created", "cash", "positions")}, ensure_ascii=False, indent=1))
    cl = s["closed"]
    if cl:
        w = sum(1 for x in cl if x["ret"] > 0)
        print(f"청산 {len(cl)}건, 승률 {w / len(cl):.0%}, 평균 {sum(x['ret'] for x in cl) / len(cl):+.2%}, 손익 {sum(x['pnl'] for x in cl):,}원")


def test(a):
    ok, cal = trading_day(a)
    print("계좌 seq:", a.account, "| 오늘 거래일:", ok, "| 다음 영업일:", cal["nextBusinessDay"]["date"])
    print("매수 가능 금액:", won(a.buying_power()))
    h = a.holdings()
    print("보유 종목 수:", len(h.get("items", [])), "(봇은 자기 장부 종목만 관리)")
    c = a.candles("005930", count=3)["candles"]
    print("삼성전자 최근 일봉:", [(x["timestamp"][:10], x["closePrice"]) for x in c])
    print("KOSPI:", a.index_candles(count=1)["candles"][0]["closePrice"])
    tg("🔌 토스봇 연결 테스트 성공 (주문 없음)")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    lock = open(os.path.join(HERE, "state", "lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("다른 작업 실행 중 → 종료"); return
    s = load_state()
    if cmd == "status":
        return status(s)
    if cmd == "mode":
        m = sys.argv[2]
        if m == "live" and input("실제 돈으로 주문합니다. 계속하려면 '실전' 입력: ").strip() != "실전":
            print("취소"); return
        s["mode"] = m; save_state(s); tg(f"⚙️ 토스봇 모드 변경 → {m}"); print("모드:", m); return
    try:
        a = api()
        {"test": lambda: test(a), "evening": lambda: evening(a, s), "open": lambda: place_open(a, s),
         "confirm": lambda: confirm(a, s)}[cmd]()
    except Exception as e:
        log("오류", traceback.format_exc())
        tg(f"🚨 토스봇 오류 ({cmd}): {type(e).__name__}: {str(e)[:300]}")
        raise


if __name__ == "__main__":
    main()
