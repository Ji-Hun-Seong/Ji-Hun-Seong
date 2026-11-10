"""토스증권 자동매매 봇 — 한국: 자사주 공시 스윙 / 미국: 나스닥 변동성 맞춤 레버리지

사용법 (서버, ~/ji-hun-seong/toss-bot 에서):
  .venv/bin/python bot.py test          연결 점검 (주문 없음)
  .venv/bin/python bot.py watch         [한국] 07:30~20:00 DART 공시를 30초마다 확인 → 자사주 공시 즉시 매수
  .venv/bin/python bot.py kr_open       [한국] 08:45 장 시작 동시호가 주문 (매도 예정 + 전날 밤 공시 매수)
  .venv/bin/python bot.py kr_confirm    [한국] 09:10 동시호가 체결 확인
  .venv/bin/python bot.py kr_close      [한국] 15:40 보유일·RSI 확인 → 내일 매도 예정, 일일 보고
  .venv/bin/python bot.py us_rebalance  [미국] 주 1회(화 00:10, 미국 월요일 장중) TQQQ 비중 조정
  .venv/bin/python bot.py status        장부 출력
  .venv/bin/python bot.py mode live|paper
  touch STOP                            새 주문 전부 중지 (긴급 정지)

전략 근거: backtest/research/README.md 6차(미국), 7차(한국)
- 한국: 코스피 보통주의 자기주식 취득결정·신탁계약체결결정 원공시(정정 제외), 20일 평균 거래대금 3억 이상.
  공시 직후 지정가(현재가+0.5%, 전일 종가+5% 상한)로 매수 → 10거래일 보유, RSI14>70이면 다음 날 시가 익절.
  최대 10종목, 남는 돈은 현금. 백테스트 연 13.6%(다음 날 시가 진입) ~ 25.4%(공시일 종가 진입 상한), 손실 연도 없음.
- 미국: 나스닥100(QQQ)이 200일선 위면 레버리지 = min(2, 45% / 최근 20일 변동성), 아래면 현금.
  TQQQ 비중 = 레버리지/3, 주 1회 조정(차이 5%p 이상일 때만). 10년 연 24.0% vs 나스닥100 17.9%.

안전장치: 봇 장부 종목·수량만 매도 / 운용 한도 / 투자경고·과열 종목 제외 / clientOrderId 멱등키 / 장부 파일 잠금 / STOP 파일
"""
import contextlib, datetime as dt, fcntl, json, math, os, re, sys, time, traceback
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from toss_api import Toss, TossError

KST = dt.timezone(dt.timedelta(hours=9))
STATE_DIR = os.path.join(HERE, "state")
os.makedirs(STATE_DIR, exist_ok=True)
STATE = os.path.join(STATE_DIR, "ledger.json")
LOG = os.path.join(STATE_DIR, "bot.log")
DET = os.path.join(STATE_DIR, "detections.jsonl")      # 공시 감지 기록(속도·가격 측정용)
DART = "https://opendart.fss.or.kr/api"
PAPER_SLIP = 0.003                                     # 가상 체결 시 불리하게 0.3% 가정
KR_FEE_BUY, KR_FEE_SELL = 0.00015, 0.00015 + 0.0018   # 수수료 + 매도 거래세(근사)


def load_env():
    p = os.path.join(HERE, ".env")
    if os.path.exists(p):
        for line in open(p):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.split(" #")[0].strip().strip('"').strip("'"))


load_env()
CFG = dict(
    kr_capital=float(os.environ.get("KR_CAPITAL") or os.environ.get("BOT_CAPITAL") or 3_000_000),
    kr_slots=int(os.environ.get("KR_SLOTS") or os.environ.get("MAX_POSITIONS") or 10),
    kr_hold=int(os.environ.get("KR_HOLD_DAYS") or 10),
    kr_min_tv=float(os.environ.get("KR_MIN_TV") or 3e8),
    kr_chase=float(os.environ.get("KR_MAX_CHASE") or 0.05),
    us_capital=float(os.environ.get("US_CAPITAL_USD") or 2000),
    us_symbol=os.environ.get("US_SYMBOL") or "TQQQ",
)


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
        log("[텔레그램 미설정]", text[:300]); return
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


# ── 장부 (여러 작업이 동시에 고쳐도 안전하게 파일 잠금) ──────────────
def _blank():
    return {"mode": "paper", "created": now().date().isoformat(),
            "kr": {"cash": CFG["kr_capital"], "positions": {}, "pending": [], "sell_next": [], "closed": [], "equity": []},
            "us": {"cash": CFG["us_capital"], "qty": 0.0, "avg": 0.0, "history": []},
            "seen": {}}


@contextlib.contextmanager
def ledger():
    with open(STATE + ".lock", "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        s = json.load(open(STATE)) if os.path.exists(STATE) else _blank()
        if "kr" not in s:                       # 예전(돌파 전략) 장부 → 새 형식으로
            old = s; s = _blank(); s["mode"] = old.get("mode", "paper")
        yield s
        tmp = STATE + ".tmp"
        json.dump(s, open(tmp, "w"), ensure_ascii=False, indent=1)
        os.replace(tmp, STATE)


def peek():
    return json.load(open(STATE)) if os.path.exists(STATE) else _blank()


def stopped():
    return os.path.exists(os.path.join(HERE, "STOP"))


def api():
    a = Toss(os.environ["TOSS_CLIENT_ID"], os.environ["TOSS_CLIENT_SECRET"], os.path.join(STATE_DIR, "token.json"),
             os.environ.get("TOSS_ACCOUNT_SEQ"))
    if not a.account:
        accs = a.accounts() or []
        if not accs:
            raise RuntimeError("종합매매 계좌가 없습니다")
        a.account = accs[0]["accountSeq"]
    return a


def won(x):
    return f"{x:,.0f}원"


def tick(p):
    """코스피 호가 단위로 내림"""
    t = 1 if p < 2000 else 5 if p < 5000 else 10 if p < 20000 else 50 if p < 50000 else 100 if p < 200000 else 500 if p < 500000 else 1000
    return int(p // t * t)


def kr_session(a):
    """오늘 국내 장 정보: (거래일 여부, 정규장 시작/끝, 애프터 끝, 다음 영업일)"""
    cal = a.calendar()
    t = cal["today"]; ig = t.get("integrated") or {}
    reg = ig.get("regularMarket") or {}
    aft = ig.get("afterMarket") or {}
    p = lambda x: dt.datetime.fromisoformat(x) if x else None
    return {"open": bool(reg), "start": p(reg.get("startTime")), "end": p(reg.get("endTime")),
            "after_end": p(aft.get("endTime")), "next": cal["nextBusinessDay"]["date"], "today": t["date"]}


def daily(a, sym, n=40):
    cs, before = [], None
    while len(cs) < n:
        r = a.candles(sym, count=min(200, n - len(cs)), before=before) or {}
        cs += r.get("candles", [])
        before = r.get("nextBefore")
        if not before or not r.get("candles"):
            break
    return [(c["timestamp"][:10], float(c["openPrice"]), float(c["highPrice"]), float(c["lowPrice"]),
             float(c["closePrice"]), float(c["volume"])) for c in cs][::-1]   # 과거 → 최신


def rsi14(closes):
    if len(closes) < 16:
        return None
    up = dn = 0.0
    a = 1 / 14
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        up = (1 - a) * up + a * max(d, 0); dn = (1 - a) * dn + a * max(-d, 0)
    return 100.0 if dn == 0 else 100 - 100 / (1 + up / dn)


# ── 한국: DART 공시 감시 ───────────────────────────────────────
BB = [("자사주 신탁계약", r"자기주식취득신탁계약체결결정"), ("자사주 취득", r"^(주요사항보고서\()?자기주식취득결정")]


def dart_today(key, day):
    out = []
    for ty in ("B", "I"):
        page = 1
        while True:
            j = requests.get(f"{DART}/list.json", params={"crtfc_key": key, "corp_cls": "Y", "pblntf_ty": ty,
                             "bgn_de": day, "end_de": day, "page_no": page, "page_count": 100}, timeout=20).json()
            if j.get("status") == "013":
                break
            if j.get("status") != "000":
                raise RuntimeError(f"DART {j.get('status')} {j.get('message')}")
            out += j.get("list", [])
            if page >= int(j.get("total_page", 1)):
                break
            page += 1
    return out


def buyback_filings(rows):
    out, codes = [], set()
    for it in rows:
        code = it.get("stock_code") or ""
        nm = re.sub(r"\s+", "", it.get("report_nm", ""))
        if not code.endswith("0") or nm.startswith("["):          # 보통주만, 정정·첨부 제외
            continue
        for kind, pat in BB:
            if re.search(pat, nm) and code not in codes:             # 같은 날 같은 종목(주요사항+거래소 중복) 1번만
                codes.add(code)
                out.append({"rcept_no": it["rcept_no"], "code": code, "name": it.get("corp_name", code), "kind": kind})
    return out


def kr_buy_now(a, s, f, sess, t):
    """공시 1건 처리: 조건 확인 → 지금 매수(장중·애프터) 또는 내일 시가 예약"""
    code = f["code"]
    k = s["kr"]
    if code in k["positions"] or any(p["code"] == code for p in k["pending"]):
        return f"{f['name']} 이미 보유/예약 → 건너뜀"
    if len(k["positions"]) + len(k["pending"]) >= CFG["kr_slots"]:
        return f"{f['name']} 자리 없음({CFG['kr_slots']}종목 보유 중)"
    bars = daily(a, code, 25)
    if len(bars) < 21:
        return f"{f['name']} 일봉 부족"
    today = t.date().isoformat()
    hist = [b for b in bars if b[0] < today] or bars
    prev_close = hist[-1][4]
    tv20 = sum(b[4] * b[5] for b in hist[-20:]) / 20
    if tv20 < CFG["kr_min_tv"]:
        return f"{f['name']} 거래대금 부족(20일 평균 {tv20 / 1e8:.1f}억)"
    w = [x["warningType"] for x in (a.warnings(code) or [])
         if x["warningType"] in ("LIQUIDATION_TRADING", "OVERHEATED", "INVESTMENT_WARNING", "INVESTMENT_RISK")]
    if w:
        return f"{f['name']} 투자유의({','.join(w)}) → 제외"
    last = float(a.prices([code])[0]["lastPrice"])
    cap = prev_close * (1 + CFG["kr_chase"])
    slot = min(CFG["kr_capital"] / CFG["kr_slots"], k["cash"])
    qty = math.floor(slot / (cap * (1 + KR_FEE_BUY)))
    if qty < 1:
        return f"{f['name']} 예산 부족(1주 {won(cap)})"
    in_regular = sess["open"] and sess["start"] <= t <= sess["end"] - dt.timedelta(minutes=10)
    in_after = sess["open"] and sess["end"] < t <= (sess["after_end"] or sess["end"])
    nxt = False
    if in_after:
        info = (a.stock_info([code]) or [{}])[0]
        nxt = bool((info.get("koreanMarketDetail") or {}).get("nxtSupported"))
    rec = {"code": code, "name": f["name"], "rcept_no": f["rcept_no"], "detected": t.isoformat(timespec="seconds"),
           "prev_close": prev_close, "last": last, "qty": qty}
    if (in_regular or (in_after and nxt)):
        if last > cap:
            return f"{f['name']} 이미 +{last / prev_close - 1:.1%} 올라 추격 안 함(상한 +{CFG['kr_chase']:.0%})"
        limit = tick(min(cap, last * 1.005))                  # 현재가 +0.5% 지정가 (전일 종가+5% 상한)
        if s["mode"] == "live" and not stopped():
            try:
                r = a.order(code, "BUY", qty, f"{today}-B-{code}", order_type="LIMIT", tif="DAY", price=limit)
                k["pending"].append({**rec, "how": "now", "order_id": r["orderId"], "limit": limit,
                                     "placed": t.isoformat(timespec="seconds")})
                return f"🔺 {f['name']} {qty}주 지정가 {won(limit)} 주문 (현재 {won(last)}, 전일比 {last / prev_close - 1:+.1%})"
            except TossError as e:
                log("즉시 주문 실패 → 내일 시가로", code, e)
        elif s["mode"] == "paper":
            px = min(limit, last * (1 + PAPER_SLIP))
            kr_fill(s, rec, px, qty, today, "공시 직후 " + ("장중" if in_regular else "애프터마켓"))
            return f"🧪 {f['name']} {qty}주 @ {won(px)} 가상 매수 (전일比 {px / prev_close - 1:+.1%})"
    # 장 마감 후(NXT 미지원)·장 시작 전·휴장일 → 다음 거래일 시가, 전일 종가+5% 지정가(갭이 크면 안 삼)
    day_for = today if (sess["open"] and t < sess["start"]) else sess["next"]
    k["pending"].append({**rec, "how": "open", "for": day_for})
    return f"⏰ {f['name']} {qty}주 → {day_for} 시가 매수 예약 (상한 {won(tick(cap))})"


def kr_fill(s, rec, px, qty, day, how):
    k = s["kr"]
    cost = px * qty * (1 + KR_FEE_BUY)
    k["cash"] -= cost
    k["positions"][rec["code"]] = {"name": rec["name"], "qty": qty, "entry": px, "cost": cost, "date": day,
                                   "days": 0, "rcept_no": rec.get("rcept_no"), "how": how, "last": px}


def watch(a):
    key = os.environ.get("DART_API_KEY")
    if not key:
        tg("⚠️ 토스봇: .env에 DART_API_KEY가 없어 공시 감시를 못 합니다"); return
    sess = kr_session(a)
    day = now().strftime("%Y%m%d")
    stop_at = now().replace(hour=20, minute=5, second=0)
    log("공시 감시 시작", day, "거래일" if sess["open"] else "휴장일")
    errs = 0
    while now() < stop_at:
        try:
            rows = dart_today(key, day)
            fs = buyback_filings(rows)
            with ledger() as s:
                seen = set(s["seen"].get(day, []))
                new = [f for f in fs if f["rcept_no"] not in seen]
                msgs = []
                for f in new:
                    t = now()
                    try:
                        m = kr_buy_now(a, s, f, sess, t)
                    except Exception as e:
                        m = f"{f['name']} 처리 실패: {type(e).__name__} {str(e)[:120]}"
                    seen.add(f["rcept_no"])
                    msgs.append(f"■ {f['name']} ({f['code']}) {f['kind']}\n  감지 {t:%H:%M:%S} · {m}\n"
                                f"  https://dart.fss.or.kr/dsaf001/main.do?rcpNo={f['rcept_no']}")
                    with open(DET, "a") as fh:
                        fh.write(json.dumps({"t": t.isoformat(), **f, "result": m}, ensure_ascii=False) + "\n")
                s["seen"] = {d: v for d, v in s["seen"].items() if d >= (now() - dt.timedelta(days=7)).strftime("%Y%m%d")}
                s["seen"][day] = sorted(seen)
            if msgs:
                tg(f"📢 <b>자사주 공시</b> [{'💰 실전' if peek()['mode'] == 'live' else '🧪 가상'}]\n\n" + "\n\n".join(msgs))
            errs = 0
            process_late(a, sess)
            check_now_orders(a)
        except Exception as e:
            errs += 1
            log("감시 오류", type(e).__name__, str(e)[:200])
            if errs in (3, 30):
                tg(f"⚠️ 토스봇 공시 감시 오류 {errs}회 연속: {type(e).__name__} {str(e)[:200]}")
        time.sleep(30)
    log("공시 감시 종료")


def process_late(a, sess):
    """시가 예약인데 kr_open이 이미 지나서(08:45~09:00 공시, 서버 재시작 등) 주문이 안 나간 건 → 장중 즉시 매수로 전환"""
    t = now()
    if not sess["open"] or t < sess["start"] + dt.timedelta(minutes=1):
        return
    today = t.date().isoformat()
    msgs = []
    with ledger() as s:
        late = [p for p in s["kr"]["pending"] if p.get("how") == "open" and p["for"] <= today and not p.get("placed")]
        for p in late:
            s["kr"]["pending"].remove(p)
            m = kr_buy_now(a, s, {"code": p["code"], "name": p["name"], "rcept_no": p["rcept_no"], "kind": "자사주"}, sess, t)
            msgs.append(f"⏩ {p['name']} 시가 예약을 놓쳐 장중 매수로 전환: {m}")
    if msgs:
        tg("\n".join(msgs))


def check_now_orders(a):
    """실전: 즉시 지정가 주문 3분 지나면 체결분만 장부에 넣고 나머지 취소"""
    if peek()["mode"] != "live":
        return
    with ledger() as s:
        keep, done = [], []
        for p in s["kr"]["pending"]:
            if p.get("how") != "now" or (now() - dt.datetime.fromisoformat(p["placed"])).total_seconds() < 180:
                keep.append(p); continue
            d = a.get_order(p["order_id"])
            if d["status"] in ("PENDING", "PARTIAL_FILLED"):
                with contextlib.suppress(TossError):
                    a.cancel(p["order_id"])
                time.sleep(1); d = a.get_order(p["order_id"])
            ex = d["execution"]; q = int(float(ex.get("filledQuantity") or 0))
            if q:
                kr_fill(s, p, float(ex["averageFilledPrice"]), q, now().date().isoformat(), "공시 직후 지정가")
                done.append(f"✅ {p['name']} {q}주 @ {won(float(ex['averageFilledPrice']))} 체결")
            else:
                done.append(f"⚠️ {p['name']} 미체결 → 취소 (가격이 너무 올랐음)")
        s["kr"]["pending"] = keep
    if done:
        tg("\n".join(done))


# ── 한국: 장 시작 동시호가 ─────────────────────────────────────
def kr_open(a):
    sess = kr_session(a)
    if not sess["open"]:
        log("휴장일"); return
    if stopped():
        tg("⛔ STOP 파일이 있어 오늘 시가 주문을 내지 않았습니다"); return
    today = now().date().isoformat()
    with ledger() as s:
        k = s["kr"]; live = s["mode"] == "live"; L = []
        for x in k["sell_next"]:
            p = k["positions"].get(x["code"])
            if not p or x.get("placed"):
                continue
            if live:
                q = min(p["qty"], a.sellable(x["code"]))       # 봇 장부 수량 이상은 절대 안 팜
                if q > 0:
                    r = a.order(x["code"], "SELL", q, f"{today}-S-{x['code']}", order_type="MARKET", tif="OPG")
                    x["order_id"] = r["orderId"]; x["qty"] = q
            x["placed"] = today
            L.append(f"🔻 매도 {p['name']} {p['qty']}주 ({x['why']})")
        for p in k["pending"]:
            if p.get("how") != "open" or p["for"] > today or p.get("placed"):
                continue
            limit = tick(p["prev_close"] * (1 + CFG["kr_chase"]))
            if live:
                r = a.order(p["code"], "BUY", p["qty"], f"{today}-B-{p['code']}", order_type="LIMIT", tif="OPG", price=limit)
                p["order_id"] = r["orderId"]
            p["placed"] = today; p["limit"] = limit
            L.append(f"🔺 매수 {p['name']} {p['qty']}주 (상한 {won(limit)})")
    if L:
        tg(f"{'💰' if live else '🧪'} <b>토스봇 시가 주문</b> {today}\n" + "\n".join(L))


def kr_confirm(a):
    sess = kr_session(a)
    if not sess["open"]:
        return
    today = now().date().isoformat()
    with ledger() as s:
        k = s["kr"]; live = s["mode"] == "live"; L = []
        for x in [x for x in k["sell_next"] if x.get("placed") == today]:
            p = k["positions"].get(x["code"])
            if not p:
                continue
            if live:
                ex = a.get_order(x["order_id"])["execution"]; q = int(float(ex.get("filledQuantity") or 0))
                px = float(ex["averageFilledPrice"]) if q else None
            else:
                bars = daily(a, x["code"], 1); q = p["qty"]
                px = bars[-1][1] * (1 - PAPER_SLIP) if bars and bars[-1][0] == today else None
            if not q or not px:
                L.append(f"⚠️ {p['name']} 매도 미체결 → 내일 다시"); x.pop("placed", None); continue
            proceeds = px * q * (1 - KR_FEE_SELL)
            part = p["cost"] * q / p["qty"]
            k["cash"] += proceeds
            k["closed"].append({"code": x["code"], "name": p["name"], "in": p["date"], "out": today,
                                "ret": round(proceeds / part - 1, 4), "pnl": round(proceeds - part), "why": x["why"]})
            L.append(f"🔻 {p['name']} {q}주 @ {won(px)} → {proceeds / part - 1:+.1%} ({won(proceeds - part)})")
            if q >= p["qty"]:
                del k["positions"][x["code"]]
            else:
                p["cost"] -= part; p["qty"] -= q
            x["done"] = True
        k["sell_next"] = [x for x in k["sell_next"] if not x.get("done")]
        keep = []
        for p in k["pending"]:
            if p.get("how") != "open" or p.get("placed") != today:
                keep.append(p); continue
            if live:
                ex = a.get_order(p["order_id"])["execution"]; q = int(float(ex.get("filledQuantity") or 0))
                px = float(ex["averageFilledPrice"]) if q else None
            else:
                bars = daily(a, p["code"], 1)
                o = bars[-1][1] if bars and bars[-1][0] == today else None
                q, px = (p["qty"], o * (1 + PAPER_SLIP)) if o and o <= p["limit"] else (0, None)
            if q and px:
                kr_fill(s, p, px, q, today, "다음 날 시가")
                L.append(f"🔺 {p['name']} {q}주 @ {won(px)} (전일比 {px / p['prev_close'] - 1:+.1%})")
            else:
                L.append(f"⏭ {p['name']} 시가가 상한({won(p['limit'])}) 넘어 안 삼")
        k["pending"] = keep
    if L:
        tg(f"✅ <b>토스봇 체결</b> {today} [{'💰 실전' if live else '🧪 가상'}]\n" + "\n".join(L))


def kr_close(a):
    sess = kr_session(a)
    if not sess["open"]:
        return
    today = now().date().isoformat()
    with ledger() as s:
        k = s["kr"]; L = []
        for code, p in k["positions"].items():
            bars = daily(a, code, 40)
            if not bars:
                continue
            closes = [b[4] for b in bars]
            p["last"] = closes[-1]
            if p["date"] < today:
                p["days"] = p.get("days", 0) + 1
            r = rsi14(closes)
            why = (f"RSI {r:.0f} > 70 익절" if r and r > 70 else
                   f"{CFG['kr_hold']}거래일 보유 완료" if p["days"] >= CFG["kr_hold"] else None)
            if why and not any(x["code"] == code for x in k["sell_next"]):
                k["sell_next"].append({"code": code, "why": why})
            L.append(f"▪ {p['name']} {p['qty']}주 {p['last'] / p['entry'] - 1:+.1%} · {p['days']}일째 · RSI {r or 0:.0f}"
                     + (f" → 내일 매도({why})" if why else ""))
        eq = k["cash"] + sum(p["qty"] * p["last"] for p in k["positions"].values())
        k["equity"].append([today, round(eq)])
        with contextlib.suppress(Exception):                       # 대시보드용 미국 평가 기록
            u = s["us"]; upx = float(a.prices([CFG["us_symbol"]])[0]["lastPrice"])
            u.setdefault("equity", []).append([today, round(u["cash"] + u["qty"] * upx, 2)])
        cl = k["closed"]
        mode = s["mode"]
        days_run = (now().date() - dt.date.fromisoformat(s["created"])).days
        pend = [p for p in k["pending"] if p.get("how") == "open"]
    head = [f"📈 <b>토스봇 한국 마감 보고</b> {today} [{'💰 실전' if mode == 'live' else '🧪 가상'}]",
            f"평가 {won(eq)} (원금 {won(CFG['kr_capital'])}, {eq / CFG['kr_capital'] - 1:+.1%}) · 현금 {won(k['cash'])}",
            f"청산 {len(cl)}건" + (f", 승률 {sum(1 for x in cl if x['ret'] > 0) / len(cl):.0%}, 손익 {won(sum(x['pnl'] for x in cl))}" if cl else "")]
    if L:
        head += ["", "<b>보유</b>"] + L
    if pend:
        head += ["", "<b>내일 시가 매수 예약</b>"] + [f"▪ {p['name']} {p['qty']}주" for p in pend]
    if mode == "paper" and days_run >= 14:
        head += ["", f"🧪 가상 운용 {days_run}일째 — 결과가 괜찮으면 서버에서 <code>.venv/bin/python bot.py mode live</code>"]
    tg("\n".join(head))


# ── 미국: 나스닥 변동성 맞춤 레버리지 (주 1회) ──────────────────────
def us_rebalance(a):
    cal = a.us_calendar()
    reg = (cal["today"] or {}).get("regularMarket")
    t = now()
    if not reg or not (dt.datetime.fromisoformat(reg["startTime"]) <= t <= dt.datetime.fromisoformat(reg["endTime"]) - dt.timedelta(hours=1)):
        log("미국 정규장 아님 → 건너뜀"); return
    wk = "%d-W%02d" % t.isocalendar()[:2]
    if peek()["us"].get("week") == wk:
        log("이번 주 미국 조정 이미 함"); return
    q = daily(a, "QQQ", 230)
    closes = [b[4] for b in q if b[0] < t.date().isoformat()]          # 전 거래일까지 확정 종가
    if len(closes) < 201:
        tg("⚠️ 토스봇 미국: QQQ 일봉 부족"); return
    ma200 = sum(closes[-200:]) / 200
    rets = [closes[i] / closes[i - 1] - 1 for i in range(len(closes) - 20, len(closes))]
    m = sum(rets) / 20
    vol = math.sqrt(sum((x - m) ** 2 for x in rets) / 19) * math.sqrt(252)
    L = 0.0 if closes[-1] < ma200 else min(2.0, 0.45 / vol)
    tw = L / 3
    sym = CFG["us_symbol"]
    px = float(a.prices([sym])[0]["lastPrice"])
    with ledger() as s:
        u = s["us"]; live = s["mode"] == "live"
        eq = u["cash"] + u["qty"] * px
        cw = u["qty"] * px / eq if eq else 0
        msg = [f"🇺🇸 <b>나스닥 주간 조정</b> {t:%Y-%m-%d} [{'💰 실전' if live else '🧪 가상'}]",
               f"QQQ {closes[-1]:,.2f} / 200일선 {ma200:,.2f} → {'🟢 위' if L else '🔴 아래(현금)'}",
               f"20일 변동성 {vol:.1%} → 목표 레버리지 {L:.2f}배 = {sym} {tw:.0%}",
               f"현재 {sym} {u['qty']:.4f}주({cw:.0%}) · 평가 ${eq:,.2f}"]
        diff = tw - cw
        if abs(diff) < 0.05 or stopped():
            msg.append("변화 5%p 미만 → 그대로" if not stopped() else "⛔ STOP 파일 → 주문 안 함")
        else:
            amt = abs(diff) * eq
            side = "BUY" if diff > 0 else "SELL"
            qty = round(amt / px, 6)
            if side == "SELL":
                qty = min(qty, u["qty"])
            if live:
                cid = f"{t:%Y%m%d}-US-{side}"
                r = (a.order(sym, "BUY", client_order_id=cid, amount=min(amt, a.buying_power_usd()))
                     if side == "BUY" else a.order(sym, "SELL", qty, cid))
                time.sleep(5)
                ex = a.get_order(r["orderId"])["execution"]
                fq, fp = float(ex.get("filledQuantity") or 0), float(ex.get("averageFilledPrice") or px)
            else:
                fq, fp = qty, px * (1 + PAPER_SLIP if side == "BUY" else 1 - PAPER_SLIP)
            if side == "BUY":
                u["avg"] = (u["avg"] * u["qty"] + fp * fq) / (u["qty"] + fq) if (u["qty"] + fq) else 0
                u["qty"] += fq; u["cash"] -= fp * fq
            else:
                u["qty"] -= fq; u["cash"] += fp * fq
            u["history"].append({"date": t.date().isoformat(), "side": side, "qty": fq, "px": fp, "target": tw})
            msg.append(f"{'🔺 매수' if side == 'BUY' else '🔻 매도'} {sym} {fq:.4f}주 @ ${fp:,.2f} (${fp * fq:,.2f})")
        u["week"] = wk
        eq = u["cash"] + u["qty"] * px
        msg.append(f"조정 후 평가 ${eq:,.2f} (원금 ${CFG['us_capital']:,.0f}, {eq / CFG['us_capital'] - 1:+.1%})")
    tg("\n".join(msg))


# ── 기타 ───────────────────────────────────────────────────────
def status():
    s = peek()
    print(json.dumps({"mode": s["mode"], "created": s["created"], "kr": {k: s["kr"][k] for k in ("cash", "positions", "pending", "sell_next")},
                      "us": {k: s["us"][k] for k in ("cash", "qty", "avg")}}, ensure_ascii=False, indent=1))
    cl = s["kr"]["closed"]
    if cl:
        print(f"한국 청산 {len(cl)}건, 승률 {sum(1 for x in cl if x['ret'] > 0) / len(cl):.0%}, 손익 {sum(x['pnl'] for x in cl):,}원")


def test(a):
    sess = kr_session(a)
    print("계좌 seq:", a.account, "| 오늘 국내 거래일:", sess["open"], "| 다음 영업일:", sess["next"])
    print("매수 가능 금액(원):", won(a.buying_power()))
    with contextlib.suppress(Exception):
        print("매수 가능 금액(달러):", f"${a.buying_power_usd():,.2f}")
    print("보유 종목 수:", len((a.holdings() or {}).get("items", [])), "(봇은 자기 장부 종목만 관리)")
    print("삼성전자 최근 일봉:", [(b[0], b[4]) for b in daily(a, "005930", 3)])
    print("QQQ 최근 일봉:", [(b[0], b[4]) for b in daily(a, "QQQ", 2)], "| TQQQ 현재가:", a.prices(["TQQQ"])[0]["lastPrice"])
    key = os.environ.get("DART_API_KEY")
    if key:
        rows = dart_today(key, (now() - dt.timedelta(days=3)).strftime("%Y%m%d"))
        print("DART 연결 OK (3일 전 코스피 공시", len(rows), "건)")
    else:
        print("⚠️ DART_API_KEY 없음 → .env에 추가해야 한국 전략이 돌아감")
    tg("🔌 토스봇 연결 테스트 성공 (주문 없음)")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        return status()
    if cmd == "mode":
        m = sys.argv[2]
        if m == "live" and input("실제 돈으로 주문합니다. 계속하려면 '실전' 입력: ").strip() != "실전":
            print("취소"); return
        with ledger() as s:
            s["mode"] = m
        tg(f"⚙️ 토스봇 모드 → {m}"); print("모드:", m); return
    lock = open(os.path.join(STATE_DIR, f"{cmd}.lock"), "w")         # 같은 작업 중복 실행 방지
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return
    try:
        a = api()
        {"test": test, "watch": watch, "kr_open": kr_open, "kr_confirm": kr_confirm, "kr_close": kr_close,
         "us_rebalance": us_rebalance}[cmd](a)
    except Exception as e:
        log("오류", traceback.format_exc())
        tg(f"🚨 토스봇 오류 ({cmd}): {type(e).__name__}: {str(e)[:300]}")
        raise


if __name__ == "__main__":
    main()
