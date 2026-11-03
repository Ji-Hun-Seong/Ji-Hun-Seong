"""미국 급등주 일일 수집 — 미국 장 마감 후(한국 아침) GitHub Actions에서 실행

  1. 야후 Day Gainers 상위 250 → 급등주(+10%↑, 주가 $2↑, 시가총액 $3억↑ — 동전주 잡음 제외)
  2. 종목별 1년 일봉 → 급등 '전날까지'의 차트 특징 (한국과 같은 계산식, collect.py 재사용)
  3. SEC 공시(8-K 등, 최근 2일)와 뉴스 제목(구글 뉴스 영어) → 재료 자동 분류
  4. 과거 급등주의 +1·3·5·10거래일 수익률 추적, 리포트·텔레그램 개인 채팅 요약

저장: surge-study/data/us/daily/YYYY-MM-DD.json, data/us/surges.csv, reports/us/YYYY-MM-DD.md
환경변수: SEC_UA(이름 이메일), TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import time
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from collect import FOLLOW, classify, features, today_bar, update_follow  # noqa: E402

DATA = os.path.join(HERE, "data", "us")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36"}
REPO_URL = "https://github.com/Ji-Hun-Seong/Ji-Hun-Seong/blob/main/surge-study"
SURGE_PCT, MIN_PRICE, MIN_MCAP = 10.0, 2.0, 3e8

CATALYST_US = [
    ("Earnings", r"earnings|results|revenue|EPS|guidance|beats?|tops estimates|quarter"),
    ("FDA·Clinical", r"FDA|trial|phase|approval|clearance|data readout|study"),
    ("M&A", r"acquire|acquisition|merger|buyout|takeover|to be acquired|deal to buy|tender offer"),
    ("Contract·Partnership", r"contract|partnership|agreement|collaborat|award|order"),
    ("Analyst", r"upgrade|price target|initiat|outperform|overweight|buy rating"),
    ("Product·Tech", r"launch|unveil|AI|chip|breakthrough|patent"),
    ("Guidance·Buyback", r"buyback|repurchase|raises outlook|raises guidance|dividend"),
    ("Policy·Macro", r"tariff|government|Trump|White House|regulat|Fed|subsid"),
    ("Short squeeze·Meme", r"short squeeze|meme|retail traders|Reddit"),
]
SEC_ITEMS = {"1.01": "계약 체결", "2.02": "실적 발표", "5.02": "임원 변동", "7.01": "IR 자료", "8.01": "기타 중요사항",
             "1.02": "계약 해지", "2.01": "자산 인수·처분", "3.02": "주식 발행", "5.07": "주총 결과", "9.01": "재무제표·첨부"}


def gainers() -> list[dict]:
    j = requests.get("https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved", headers=UA, timeout=20,
                     params={"scrIds": "day_gainers", "count": 250, "formatted": "false"}).json()
    return j["finance"]["result"][0]["quotes"]


def yahoo_daily(sym: str, rng: str = "1y") -> pd.DataFrame | None:
    try:
        r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}", headers=UA, timeout=20,
                         params={"range": rng, "interval": "1d"})
        res = r.json()["chart"]["result"][0]
        q = res["indicators"]["quote"][0]
        idx = pd.to_datetime(res["timestamp"], unit="s", utc=True).tz_convert("America/New_York").tz_localize(None).normalize()
        df = pd.DataFrame({k: q[k] for k in ("open", "high", "low", "close", "volume")}, index=idx).dropna(subset=["close"])
        return df[~df.index.duplicated(keep="last")]
    except Exception:
        return None


def sec_map(ua: str) -> dict[str, int]:
    try:
        j = requests.get("https://www.sec.gov/files/company_tickers.json", headers={"User-Agent": ua}, timeout=30).json()
        return {v["ticker"].upper(): int(v["cik_str"]) for v in j.values()}
    except Exception:
        return {}


def sec_filings(cik: int, ua: str, since: str) -> list[dict]:
    try:
        j = requests.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", headers={"User-Agent": ua}, timeout=20).json()
        r = j["filings"]["recent"]
        out = []
        for i, d in enumerate(r["filingDate"]):
            if d < since:
                break
            items = r.get("items", [""] * len(r["form"]))[i]
            out.append({"date": d, "form": r["form"][i], "items": items,
                        "items_kr": ", ".join(SEC_ITEMS.get(x.strip(), x.strip()) for x in items.split(",") if x.strip()),
                        "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{r['accessionNumber'][i].replace('-', '')}/{r['primaryDocument'][i]}"})
        return out[:8]
    except Exception:
        return []


def news_en(sym: str, name: str, n: int = 6) -> list[dict]:
    try:
        q = f'"{sym}" stock when:2d'
        r = requests.get("https://news.google.com/rss/search", headers=UA, timeout=15,
                         params={"q": q, "hl": "en-US", "gl": "US", "ceid": "US:en"})
        out = []
        for it in ElementTree.fromstring(r.content).iter("item"):
            out.append({"title": (it.findtext("title") or "").strip(), "date": it.findtext("pubDate") or ""})
            if len(out) >= n:
                break
        return out
    except Exception:
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-send", action="store_true")
    a = ap.parse_args()
    ua = os.environ.get("SEC_UA", "").strip() or "research bot contact@example.com"
    os.makedirs(os.path.join(DATA, "daily"), exist_ok=True)
    os.makedirs(os.path.join(HERE, "reports", "us"), exist_ok=True)

    qs = gainers()
    if not qs:
        print("Day Gainers 비어 있음 — 종료"); return
    t_market = dt.datetime.fromtimestamp(max(q.get("regularMarketTime", 0) for q in qs), ZoneInfo("America/New_York"))
    day = t_market.strftime("%Y-%m-%d")
    if os.path.exists(os.path.join(DATA, "daily", f"{day}.json")):
        print(f"{day} 이미 수집함 — 건너뜀"); return
    cand = [q for q in qs if (q.get("regularMarketChangePercent") or 0) >= SURGE_PCT
            and (q.get("regularMarketPrice") or 0) >= MIN_PRICE and (q.get("marketCap") or 0) >= MIN_MCAP]
    print(f"{day} 상승 상위 {len(qs)} · 조건 충족 급등주 {len(cand)}", flush=True)

    tick = sec_map(ua)
    since = (t_market.date() - dt.timedelta(days=3)).isoformat()
    surgers, frames = [], {}
    for q in cand:
        sym = q["symbol"]
        df = yahoo_daily(sym)
        if df is None or len(df) < 26 or f"{df.index[-1]:%Y-%m-%d}" != day:
            continue
        frames[sym] = df
        f = features(df.iloc[:-1].assign(fr=np.nan))
        tb = today_bar(df)
        fl = sec_filings(tick[sym.upper()], ua, since) if sym.upper() in tick else []
        nw = news_en(sym, q.get("shortName", ""))
        texts = [x["title"] for x in nw]
        cats = classify(texts, CATALYST_US)
        if any("2.02" in x["items"] for x in fl) and "Earnings" not in cats:
            cats.insert(0, "Earnings")
        if any("1.01" in x["items"] for x in fl) and "Contract·Partnership" not in cats:
            cats.append("Contract·Partnership")
        surgers.append({"date": day, "code": sym, "name": q.get("shortName") or q.get("longName", ""),
                        "market": q.get("fullExchangeName", ""), "sector": q.get("sector", ""),
                        "mcap": q.get("marketCap"), **tb, **f, "filings": fl, "news": nw, "catalysts": cats,
                        "vol_ratio": tb["vol_ratio"]})
        time.sleep(0.4)
    surgers.sort(key=lambda s: -s["chg"])
    ctx = {"n_gainers_list": len(qs), "n_surge": len(surgers), "asof": t_market.isoformat(timespec="minutes")}
    out = {"date": day, "context": ctx, "surgers": surgers}
    json.dump(out, open(os.path.join(DATA, "daily", f"{day}.json"), "w"), ensure_ascii=False, indent=1, default=float)

    sp = os.path.join(DATA, "surges.csv")
    keep = ["date", "code", "name", "market", "sector", "mcap", "chg", "gap", "high_chg", "close_pos", "upper_wick", "tv",
            "vol_ratio", "close", "pctb", "bw_pctile", "squeeze", "rsi14", "ma20_gap", "ma_aligned", "ret5", "ret20",
            "from_high", "vol_ratio_prev", "prev_chg", "up_days"]
    new = pd.DataFrame([{k: s.get(k) for k in keep} | {"catalysts": "|".join(s["catalysts"]), "sec_n": len(s["filings"])}
                        for s in surgers])
    S = pd.read_csv(sp) if os.path.exists(sp) else pd.DataFrame()
    S = pd.concat([S[S["date"] != day] if not S.empty else S, new], ignore_index=True)
    if not S.empty:                                   # 지난 급등주 이후 수익률 갱신
        need = S[S[[f"ret_{k}d" for k in FOLLOW if f"ret_{k}d" in S]].isna().any(axis=1)]["code"].unique() \
            if any(f"ret_{k}d" in S for k in FOLLOW) else S["code"].unique()
        closes = {s: frames[s]["close"] for s in frames}
        for sym in need:
            if sym not in closes:
                df = yahoo_daily(sym, "3mo")
                if df is not None:
                    closes[sym] = df["close"]
                time.sleep(0.2)
        S = update_follow(S, closes)
    S.to_csv(sp, index=False, float_format="%.5g")
    write_report(out, S)
    if not a.no_send:
        send(out)
    print("완료:", day)


def write_report(out, S):
    d, sur = out["date"], out["surgers"]
    pct = lambda v: "-" if v is None or v != v else f"{v * 100:+.0f}%"
    L = [f"# 미국 급등주 리포트 · {d} (현지)", "",
         f"> 조건(+{SURGE_PCT:.0f}%↑, ${MIN_PRICE:.0f}↑, 시총 $3억↑) 충족 **{len(sur)}종목** · 기준 {out['context']['asof']}", "",
         "[목차](../../README.md) · [미국 분석 노트](../../notes/us/) · [패턴 정리](../../PATTERNS.md)", "",
         "| 종목 | 등락 | 갭 | 종가위치 | 시총 | 거래량배수 | 재료(자동) | SEC 공시 |", "|---|--:|--:|--:|--:|--:|---|---|"]
    for s in sur:
        sec = "; ".join(f"{x['form']} {x['items_kr']}".strip() for x in s["filings"][:2]) or "-"
        L.append(f"| {s['code']} {s['name'][:24]} | {s['chg']:+.1f}% | {s['gap']:+.1f}% | {s['close_pos']:.2f} | "
                 f"${(s['mcap'] or 0) / 1e9:.1f}B | {(s['vol_ratio'] or 0):.1f}x | {', '.join(s['catalysts']) or '-'} | {sec} |")
    L += ["", "## 급등 전날의 모습", "", "| 종목 | %b | 밴드폭 하위% | RSI | 20일 수익률 | 고점 대비 | 전일 거래량배수 |",
          "|---|--:|--:|--:|--:|--:|--:|"]
    for s in sur:
        L.append(f"| {s['code']} | {s.get('pctb') or 0:.2f} | {(s.get('bw_pctile') or 0) * 100:.0f} | {s.get('rsi14') or 0:.0f} | "
                 f"{pct(s.get('ret20'))} | {pct(s.get('from_high'))} | {(s.get('vol_ratio_prev') or 0):.1f}x |")
    L += ["", "## 뉴스 제목", ""]
    for s in sur[:15]:
        L += [f"**{s['code']}** {s['chg']:+.1f}%"] + [f"- {n['title']}" for n in s["news"][:3]] + [""]
    if not S.empty and "ret_5d" in S and S["ret_5d"].notna().sum() >= 5:
        dn = S.dropna(subset=["ret_5d"])
        L += ["## 누적 통계", "", f"- 표본 {len(dn)} · 5거래일 뒤 평균 {dn['ret_5d'].mean():+.1f}% · 플러스 비율 {(dn['ret_5d'] > 0).mean() * 100:.0f}%", ""]
    L += ["---", "", "※ 재료는 뉴스 제목·SEC 항목으로 자동 분류. 투자 권유 아님.", ""]
    open(os.path.join(HERE, "reports", "us", f"{d}.md"), "w", encoding="utf-8").write("\n".join(L))


def send(out):
    tok, chat = (os.environ.get("TELEGRAM_TOKEN") or "").strip(), (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    if not tok or not chat or chat.startswith("-"):
        print("텔레그램 생략(미설정 또는 그룹 ID)"); return
    L = [f"🇺🇸 <b>미국 급등주 {out['date']}</b> — {len(out['surgers'])}종목 (+{SURGE_PCT:.0f}%↑, 시총 $3억↑)", ""]
    for s in out["surgers"][:8]:
        L.append(f"• <b>{html.escape(s['code'])}</b> {s['chg']:+.1f}% · {html.escape(', '.join(s['catalysts'][:2]) or '재료 미확인')}")
    L += ["", f"<a href=\"{REPO_URL}/reports/us/{out['date']}.md\">리포트 보기</a>"]
    requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", timeout=20,
                  data={"chat_id": chat, "text": "\n".join(L), "parse_mode": "HTML", "disable_web_page_preview": "true"})


if __name__ == "__main__":
    main()
