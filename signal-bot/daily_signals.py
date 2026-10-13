"""
daily_signals.py — 코스피 일일 신호 봇 (평일 장 마감 후 텔레그램)

보내는 내용
  1) 시장: 코스피200 200일선 추세 + 시장 전체 외국인 20일 순매수 → ETF 비중 판단
  2) 모의 포트폴리오 두 개(각 가상 1천만 원, 합산 성적 함께 표시)
     A. 스퀴즈 돌파(BB·RSI): 최대 15종목, RSI<40 청산
     B. 자사주 공시 스윙(DART): 자사주 취득·신탁계약 공시 다음 날 시가 매수, 10거래일 보유 또는 RSI>70 익절
  3) 우선주 괴리: 우선주가 보통주 대비 고평가(괴리 BB 상단 & RSI>70) → 보통주로 갈아타기
  4) 외국인 60일 순매수 상위(참고)

규칙과 근거는 backtest/research/README.md (2015~2026 검증).
상태(모의 포트폴리오)는 signal-bot/state.json 에 저장하고 매일 커밋한다.

    python signal-bot/daily_signals.py              # 계산 + 텔레그램 전송 + 상태 저장
    python signal-bot/daily_signals.py --dry-run    # 전송·저장 없이 메시지만 출력
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import date, timedelta

import numpy as np
import pandas as pd
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STATE = os.path.join(HERE, "state.json")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36"}

# 전략 파라미터(백테스트와 동일)
MAX_POS = 15
SQ_Q, SQ_WIN, RSI_IN, RSI_OUT = 0.2, 5, 60, 40
UNIVERSE_N = 200
BUY_COST = 0.00015 + 0.001
SELL_COST = 0.00015 + 0.002 + 0.001
START_CASH = 10_000_000
PREF_LIQ = 3e8
# 자사주 공시 스윙(백테스트 2015~2026: 연 12.9%, MDD -29%, Sharpe 1.01 / 스퀴즈와 50:50 합산 연 15.9%, MDD -26%, Sharpe 1.17)
BB_MAX_POS, BB_HOLD, BB_TAKE, BB_LIQ = 10, 10, 70, 3e8
DART = "https://opendart.fss.or.kr/api"


# ---------------------------------------------------------------------------
# 데이터
# ---------------------------------------------------------------------------
def kospi_listing() -> dict[str, str]:
    out = {}
    for page in range(1, 40):
        j = requests.get("https://m.stock.naver.com/api/stocks/marketValue/KOSPI",
                         params={"page": page, "pageSize": 100}, headers=UA, timeout=20).json()
        items = j.get("stocks", []) if isinstance(j, dict) else j
        if not items:
            break
        for it in items:
            if it.get("stockEndType") == "stock":
                out[it["itemCode"]] = it.get("stockName", "")
        time.sleep(0.1)
    if len(out) < 500:
        raise RuntimeError(f"코스피 종목 목록이 {len(out)}개뿐 — 네이버 응답 확인 필요")
    return out


ROW = re.compile(r'\["(\d{8})",\s*([\d.]+),\s*([\d.]+),\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\]')


def daily(code: str, start: str) -> pd.DataFrame:
    for attempt in range(3):
        try:
            r = requests.get("https://api.finance.naver.com/siseJson.naver",
                             params={"symbol": code, "requestType": 1, "timeframe": "day",
                                     "startTime": start, "endTime": date.today().strftime("%Y%m%d")},
                             headers=UA, timeout=30)
            rows = ROW.findall(r.text)
            if rows:
                break
        except requests.RequestException:
            pass
        time.sleep(1 + attempt)
    else:
        raise RuntimeError(f"{code} 시세 없음")
    df = pd.DataFrame(rows, columns=["Date", "Open", "High", "Low", "Close", "Volume", "FR"])
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date").replace("", np.nan).astype(float)
    df = df[df["Close"] > 0]
    df.loc[df["Open"] <= 0, "Open"] = df["Close"]
    return df


def load_all(start: str):
    names = kospi_listing()
    frames = {}
    for i, c in enumerate(names):
        try:
            frames[c] = daily(c, start)
        except Exception as e:
            print("skip", c, e)
        time.sleep(0.05)
        if i % 200 == 0:
            print(f"{i}/{len(names)}", flush=True)
    idx = daily("KPI200", start)["Close"]
    piv = {f: pd.DataFrame({c: d[f] for c, d in frames.items()}) for f in ["Open", "Close", "Volume", "FR"]}
    dates = idx.index
    piv = {f: v.reindex(dates) for f, v in piv.items()}
    return names, piv, idx


# ---------------------------------------------------------------------------
# 지표
# ---------------------------------------------------------------------------
def rsi(c, n=14):
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def compute(names, piv, idx):
    C_all = piv["Close"]
    common = [c for c in C_all.columns if c.endswith("0")]
    C, O, V = C_all[common], piv["Open"][common], piv["Volume"][common]
    mid = C.rolling(20).mean(); sd = C.rolling(20).std()
    up = mid + 2 * sd
    bw_q = (4 * sd / mid).rolling(250, min_periods=120).rank(pct=True)
    r14 = rsi(C)
    ma50, ma200 = C.rolling(50).mean(), C.rolling(200).mean()
    mom = C.shift(5) / C.shift(126) - 1
    tv = (C * V).rolling(20).mean()

    # 유니버스: 직전 월말 기준 20일 평균 거래대금 상위 200 (상장 250거래일 이상)
    age = C.notna().cumsum()
    me = tv.where(age > 250).resample("ME").last()
    rank = me.rank(axis=1, ascending=False)
    uni = (rank <= UNIVERSE_N).shift(1).reindex(C.index, method="ffill").fillna(False).astype(bool)

    t = C.index[-1]
    squeeze = bw_q.rolling(SQ_WIN).min() < SQ_Q
    entry = squeeze & (C > up) & (r14 > RSI_IN) & (ma50 > ma200) & uni
    regime = bool(idx.iloc[-1] > idx.rolling(200).mean().iloc[-1])

    # 외국인: 보유율(소진율) 변화, 공표 시차로 하루 늦게 사용
    FR = piv["FR"][common].where(piv["FR"][common] > 0).ffill(limit=3).shift(1)
    dfr20, dfr60 = FR - FR.shift(20), FR - FR.shift(60)
    w = tv.where(uni)
    agg = (dfr20 * w).sum(axis=1) / w.where(dfr20.notna()).sum(axis=1)

    # 우선주 괴리
    prefs = [c for c in C_all.columns if not c.endswith("0") and (c[:5] + "0") in C_all.columns]
    pref_rows = []
    if prefs:
        P = C_all[prefs]
        Cm = C_all[[p[:5] + "0" for p in prefs]].set_axis(prefs, axis=1)
        Rr = np.log(P / Cm)
        m60 = Rr.rolling(60).mean(); s60 = Rr.rolling(60).std()
        pb = (Rr - (m60 - 2 * s60)) / (4 * s60)
        rR = Rr.apply(lambda s: rsi(np.exp(s)))
        liq = (P * piv["Volume"][prefs]).rolling(20).mean()
        for p in prefs:
            if pd.isna(pb[p].iloc[-1]):
                continue
            pref_rows.append(dict(code=p, name=names.get(p, p), common=names.get(p[:5] + "0", ""),
                                  ratio=float(np.exp(Rr[p].iloc[-1])), pb=float(pb[p].iloc[-1]),
                                  rsi=float(rR[p].iloc[-1]), liquid=bool(liq[p].iloc[-1] > PREF_LIQ)))

    return dict(t=t, C=C, O=O, r14=r14, mom=mom, entry=entry, regime=regime, idx=idx, tv=tv,
                ma200_idx=float(idx.rolling(200).mean().iloc[-1]), agg=agg, dfr60=dfr60, uni=uni,
                prefs=pd.DataFrame(pref_rows))


# ---------------------------------------------------------------------------
# DART: 자사주 취득·신탁계약 공시
# ---------------------------------------------------------------------------
BUYBACK = re.compile(r"^(주요사항보고서\()?(자기주식취득결정|자기주식취득신탁계약체결결정)")


def dart_buybacks(since: date, until: date):
    """since < 접수일 <= until 인 코스피 자사주 취득·신탁계약 원공시(정정·연장 제외)."""
    key = (os.environ.get("DART_API_KEY") or "").strip()
    if not key:
        print("::warning::DART_API_KEY 없음 — 자사주 공시 전략 건너뜀")
        return None
    out, page = [], 1
    while True:
        try:
            j = requests.get(f"{DART}/list.json", params={
                "crtfc_key": key, "corp_cls": "Y", "pblntf_ty": "B",
                "bgn_de": (since + timedelta(days=1)).strftime("%Y%m%d"), "end_de": until.strftime("%Y%m%d"),
                "page_no": page, "page_count": 100}, timeout=30).json()
        except Exception as e:
            print("::warning::DART 조회 실패", e)
            return None
        if j.get("status") == "013":          # 조회 결과 없음
            break
        if j.get("status") != "000":
            print("::warning::DART 응답", j.get("status"), j.get("message"))
            return None
        for it in j.get("list", []):
            nm = re.sub(r"\s+", "", it.get("report_nm", ""))
            if BUYBACK.search(nm) and it.get("stock_code"):
                out.append({"code": it["stock_code"], "corp": it.get("corp_name", ""), "dt": it["rcept_dt"],
                            "kind": "신탁" if "신탁" in nm else "직접", "rcept_no": it["rcept_no"]})
        if page >= int(j.get("total_page", 1)):
            break
        page += 1
        time.sleep(0.2)
    return out


# ---------------------------------------------------------------------------
# 모의 포트폴리오 (신호는 종가, 체결은 다음 거래일 시가). 슬리브 A·B 각각 가상 1천만 원
# ---------------------------------------------------------------------------
def new_sleeve():
    return {"cash": START_CASH, "positions": {}, "pending_buy": [], "pending_sell": [], "trades": [], "equity": []}


def new_state(t, idx_level):
    return {"version": 2, "start": str(t.date()), "start_index": idx_level, "last_date": None,
            "sleeves": {"squeeze": new_sleeve(), "buyback": new_sleeve()}, "seen_rcept": []}


def fill_orders(sl, x, names, today, max_pos):
    C, O = x["C"], x["O"]
    filled = {"buy": [], "sell": []}
    for code in list(sl["pending_sell"]):
        p = sl["positions"].get(code)
        px = O[code].iloc[-1] if code in O else np.nan
        if p is None or not np.isfinite(px):
            continue
        proceeds = p["shares"] * px * (1 - SELL_COST)
        sl["cash"] += proceeds
        ret = proceeds / p["cost"] - 1
        sl["trades"].append({"code": code, "name": p["name"], "entry": p["date"], "exit": today, "ret": round(ret, 4)})
        filled["sell"].append((p["name"], ret))
        del sl["positions"][code]
    sl["pending_sell"] = [c for c in sl["pending_sell"] if c in sl["positions"]]
    equity_open = sl["cash"] + sum(p["shares"] * C[c].iloc[-2] for c, p in sl["positions"].items()
                                   if c in C and np.isfinite(C[c].iloc[-2]))
    for code in sl["pending_buy"]:
        if len(sl["positions"]) >= max_pos or code in sl["positions"]:
            continue
        px = O[code].iloc[-1] if code in O else np.nan
        if not np.isfinite(px):
            continue
        budget = min(sl["cash"], equity_open / max_pos)
        if budget <= 0:
            break
        sl["positions"][code] = {"name": names.get(code, code), "shares": budget / (px * (1 + BUY_COST)),
                                 "cost": budget, "entry_px": float(px), "date": today, "days": 0}
        sl["cash"] -= budget
        filled["buy"].append((names.get(code, code), float(px)))
    sl["pending_buy"] = []
    return filled


def mark(sl, x, today):
    C = x["C"]
    eq = sl["cash"] + sum(p["shares"] * C[c].iloc[-1] for c, p in sl["positions"].items()
                          if c in C and np.isfinite(C[c].iloc[-1]))
    sl["equity"].append([today, round(eq)])
    sl["equity"] = sl["equity"][-800:]
    return eq


def step(state, x, names, buybacks):
    t, C = x["t"], x["C"]
    today = str(t.date())
    if state["last_date"] == today:
        return None
    out = {}
    # A. 스퀴즈 돌파
    sl = state["sleeves"]["squeeze"]
    filled = fill_orders(sl, x, names, today, MAX_POS)
    sells = []
    for code, p in sl["positions"].items():
        p["days"] = p.get("days", 0) + 1
        r = x["r14"][code].iloc[-1]
        if np.isfinite(r) and r < RSI_OUT:
            sl["pending_sell"].append(code)
            sells.append((p["name"], f"RSI {r:.0f} < {RSI_OUT}", C[code].iloc[-1] / p["entry_px"] - 1))
    sig = [c for c in x["entry"].columns if x["entry"][c].iloc[-1]]
    sig = sorted(sig, key=lambda c: -(x["mom"][c].iloc[-1] if np.isfinite(x["mom"][c].iloc[-1]) else -9))
    buys = []
    if x["regime"]:
        slots = MAX_POS - (len(sl["positions"]) - len(sl["pending_sell"]))
        for c in sig:
            if slots <= 0:
                break
            if c in sl["positions"]:
                continue
            sl["pending_buy"].append(c)
            buys.append((names.get(c, c), f"RSI {x['r14'][c].iloc[-1]:.0f}", float(C[c].iloc[-1])))
            slots -= 1
    out["squeeze"] = dict(filled=filled, sells=sells, buys=buys, signals=[names.get(c, c) for c in sig], equity=mark(sl, x, today))

    # B. 자사주 공시 스윙
    sl = state["sleeves"]["buyback"]
    filled = fill_orders(sl, x, names, today, BB_MAX_POS)
    sells = []
    for code, p in sl["positions"].items():
        p["days"] = p.get("days", 0) + 1
        r = x["r14"][code].iloc[-1] if code in x["r14"] else np.nan
        why = f"RSI {r:.0f} > {BB_TAKE} 익절" if np.isfinite(r) and r > BB_TAKE else (f"{BB_HOLD}거래일 경과" if p["days"] >= BB_HOLD else "")
        if why:
            sl["pending_sell"].append(code)
            sells.append((p["name"], why, C[code].iloc[-1] / p["entry_px"] - 1))
    buys, events, skipped = [], [], []
    if buybacks is not None:
        seen = set(state.get("seen_rcept", []))
        fresh = [e for e in buybacks if e["rcept_no"] not in seen]
        state["seen_rcept"] = (state.get("seen_rcept", []) + [e["rcept_no"] for e in fresh])[-1000:]
        cand = []
        for e in fresh:
            c = e["code"]
            nm = names.get(c, e["corp"])
            events.append(f"{nm}({e['kind']})")
            if c not in C or not np.isfinite(C[c].iloc[-1]):
                skipped.append(f"{nm}: 시세 없음"); continue
            tvv = x["tv"][c].iloc[-1]
            if not (np.isfinite(tvv) and tvv >= BB_LIQ):
                skipped.append(f"{nm}: 거래대금 부족"); continue
            if c in sl["positions"] or c in [b for b in sl["pending_buy"]]:
                continue
            cand.append(c)
        cand = sorted(set(cand), key=lambda c: x["r14"][c].iloc[-1] if np.isfinite(x["r14"][c].iloc[-1]) else 99)
        slots = BB_MAX_POS - (len(sl["positions"]) - len(sl["pending_sell"]))
        for c in cand:
            if slots <= 0:
                skipped.append(f"{names.get(c, c)}: 자리 부족"); continue
            sl["pending_buy"].append(c)
            buys.append((names.get(c, c), f"RSI {x['r14'][c].iloc[-1]:.0f}", float(C[c].iloc[-1])))
            slots -= 1
    out["buyback"] = dict(filled=filled, sells=sells, buys=buys, events=events, skipped=skipped,
                          ok=buybacks is not None, equity=mark(sl, x, today))
    state["last_date"] = today
    return out


# ---------------------------------------------------------------------------
# 메시지
# ---------------------------------------------------------------------------
def holdings():
    path = os.path.join(ROOT, "value-bot", "holdings.txt")
    if not os.path.exists(path):
        return set()
    return {l.strip() for l in open(path, encoding="utf-8") if l.strip() and not l.startswith("#")}


def sleeve_lines(L, r, sl, x, hold):
    for nm, px in r["filled"]["buy"]:
        L.append(f"✅ 오늘 시가 매수: {nm} {px:,.0f}원")
    for nm, ret in r["filled"]["sell"]:
        L.append(f"✅ 오늘 시가 매도: {nm} ({ret:+.1%})")
    for nm, why, c in r["buys"]:
        L.append(f"🟢 내일 매수: {nm}{' 📌' if nm in hold else ''} ({why}, 종가 {c:,.0f})")
    for nm, why, pnl in r["sells"]:
        L.append(f"🔴 내일 매도: {nm} ({why}, 평가 {pnl:+.1%})")
    if not (r["buys"] or r["sells"] or r["filled"]["buy"] or r["filled"]["sell"]):
        L.append("변동 없음")
    pos = sl["positions"]
    if pos:
        L.append(f"보유 {len(pos)}종목: " + ", ".join(
            f"{p['name']} {x['C'][c].iloc[-1] / p['entry_px'] - 1:+.0%}" for c, p in pos.items() if c in x["C"]))
    eq = r["equity"]
    n = len(sl["trades"])
    tail = f" · 청산 {n}건 승률 {sum(1 for tr in sl['trades'] if tr['ret'] > 0) / n:.0%}" if n else ""
    L.append(f"평가액 {eq:,.0f}원 ({eq / START_CASH - 1:+.1%}){tail}")


def build_message(x, res, state, names):
    t = x["t"]; idx = x["idx"]; agg = x["agg"]
    lvl, ma = float(idx.iloc[-1]), x["ma200_idx"]
    a = float(agg.iloc[-1]) if np.isfinite(agg.iloc[-1]) else 0.0
    trend_up, foreign_buy = lvl > ma, a > 0
    if trend_up and foreign_buy:
        stance = "🟢 ETF 보유 (추세↑ · 외국인 순매수)"
    elif trend_up:
        stance = "🟡 ETF 비중 축소 고려 (추세↑ · 외국인 순매도)"
    else:
        stance = "🔴 ETF 현금화 고려 (추세↓)"
    streak = 0
    for v in agg.iloc[::-1]:
        if np.isfinite(v) and (v > 0) == foreign_buy:
            streak += 1
        else:
            break
    hold = holdings()
    L = [f"📈 코스피 일일 신호 · {t.strftime('%Y-%m-%d')} 종가 기준", ""]
    L += ["① 시장",
          f"코스피200 {lvl:,.1f} / 200일선 {ma:,.1f} ({lvl / ma - 1:+.1%})",
          f"외국인 20일 순매수 {a:+.2f}%p ({'순매수' if foreign_buy else '순매도'} {streak}일째)",
          stance, ""]
    S = state["sleeves"]
    if res is None:
        L += ["오늘은 이미 처리됨(휴장일 재실행)", ""]
    else:
        eqA, eqB = res["squeeze"]["equity"], res["buyback"]["equity"]
        tot = (eqA + eqB) / (2 * START_CASH) - 1
        L.append(f"💼 모의투자 합산(A+B, 시작 {state['start']}): {tot:+.1%} · 같은 기간 코스피200 {lvl / state['start_index'] - 1:+.1%}")
        L.append("")
        L.append(f"② A. 스퀴즈 돌파 (BB·RSI, 최대 {MAX_POS}종목)")
        if not x["regime"]:
            L.append("⛔ 시장 필터 꺼짐(지수 200일선 아래) → 신규 매수 없음")
        sleeve_lines(L, res["squeeze"], S["squeeze"], x, hold)
        held = {p["name"] for p in S["squeeze"]["positions"].values()}
        extra = [s for s in res["squeeze"]["signals"] if s not in {b[0] for b in res["squeeze"]["buys"]} and s not in held]
        if extra:
            why = "시장 필터로 보류된 신호" if not x["regime"] else "자리 부족으로 제외된 신호"
            L.append(f"({why}: " + ", ".join(extra[:8]) + ")")
        L.append("")
        rb = res["buyback"]
        L.append(f"③ B. 자사주 공시 스윙 (최대 {BB_MAX_POS}종목, {BB_HOLD}거래일 보유 · RSI>{BB_TAKE} 익절)")
        if not rb["ok"]:
            L.append("⚠️ DART 조회 실패 — 오늘 공시 신호 없음")
        elif rb["events"]:
            L.append("오늘 자사주 공시: " + ", ".join(rb["events"][:12]))
        else:
            L.append("오늘 자사주 취득·신탁 공시 없음")
        for msg in rb["skipped"][:6]:
            L.append(f"  · 제외 {msg}")
        sleeve_lines(L, rb, S["buyback"], x, hold)
        L.append("")

    pr = x["prefs"]
    L.append("④ 우선주 괴리 (우선주÷보통주에 BB·RSI)")
    if len(pr):
        over = pr[(pr.pb > 1) & (pr.rsi > 70) & pr.liquid]
        if len(over):
            L.append("🔁 우선주 고평가 → 보통주가 유리: " + ", ".join(f"{r['name']}(괴리 {r['ratio']:.2f}, RSI {r['rsi']:.0f})" for _, r in over.iterrows()))
        else:
            L.append("고평가 신호 없음")
        for _, r in pr[pr["name"].isin(hold)].iterrows():
            state_txt = "고평가→보통주 고려" if (r.pb > 1 and r.rsi > 70) else ("정상 복귀" if r.pb < 0.5 else "중립")
            L.append(f"📌 보유 {r['name']}: 괴리 {r['ratio']:.2f}, %b {r.pb:.2f}, RSI {r.rsi:.0f} → {state_txt}")
    L.append("")
    d60 = x["dfr60"].iloc[-1].where(x["uni"].iloc[-1]).dropna().sort_values(ascending=False).head(8)
    L.append("⑤ 외국인 60일 순매수 상위 (참고용, 매매신호 아님)")
    L.append(", ".join(f"{names.get(c, c)}{' 📌' if names.get(c, c) in hold else ''} {v:+.1f}%p" for c, v in d60.items()))
    L.append("")
    L.append("※ 모의 매매입니다. 실제 주문은 직접 판단하세요.")
    return "\n".join(L)


def send(text):
    tok = os.environ.get("TELEGRAM_TOKEN", "")
    m = re.search(r"\d{6,}:[A-Za-z0-9_-]{30,}", tok)
    tok = m.group(0) if m else tok.strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not (tok and chat):
        sys.exit("::error::TELEGRAM_TOKEN / TELEGRAM_CHAT_ID 시크릿이 없습니다.")
    chunks, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > 3800:
            chunks.append(cur); cur = ""
        cur += line + "\n"
    chunks.append(cur)
    for c in chunks:
        r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                          json={"chat_id": chat, "text": c, "disable_web_page_preview": True}, timeout=20)
        if r.status_code != 200:
            sys.exit(f"::error::텔레그램 전송 실패 {r.status_code} {r.text.replace(tok, '***')[:200]}")
        time.sleep(1)
    print(f"텔레그램 전송 완료 {len(chunks)}통")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="이미 처리한 날이어도 메시지 전송")
    a = ap.parse_args()

    start = (date.today() - timedelta(days=620)).strftime("%Y%m%d")
    names, piv, idx = load_all(start)
    x = compute(names, piv, idx)
    state = json.load(open(STATE, encoding="utf-8")) if os.path.exists(STATE) else None
    if not state or state.get("version") != 2:
        state = new_state(x["t"], float(idx.iloc[-1]))
    already = state.get("last_date") == str(x["t"].date())
    # 자사주 공시: 직전 거래일 다음 날 ~ 오늘(마지막 거래일) 접수분 → 내일 시가 매수 (백테스트와 같은 기준)
    t_prev = x["C"].index[-2].date()
    buybacks = None if already else dart_buybacks(t_prev, x["t"].date())
    res = step(state, x, names, buybacks)
    if already and not a.force:
        print("이미 처리한 거래일입니다(휴장일). 전송하지 않습니다.")
        return
    text = build_message(x, res, state, names)
    print(text)
    if a.dry_run:
        return
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    send(text)


if __name__ == "__main__":
    main()
