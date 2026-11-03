"""실시간 급등 감시 — 서버에서 상시 실행 (systemd: toss-scan)

  한국: 평일 09:00~15:35 KST, 30초마다 네이버 상승률 순위(코스피·코스닥 상위 200씩)
  미국: 평일 09:30~16:05 ET, 60초마다 야후 Day Gainers 상위 100 (주가 $2·시총 $3억 미만 제외)

잡아내는 것 (이벤트)
  first10   처음으로 +10% 돌파           limit_up  상한가 진입(한국)
  jump      직전 확인 대비 +3%p 이상 급가속 fade      장중 최고 대비 −5%p 이상 밀림

저장: state/scanner/{kr|us}-YYYY-MM-DD.json (대시보드가 읽음), state/scanner/{kr|us}-YYYY-MM-DD.csv (분 단위 기록, 연구용)
텔레그램 알림은 기본 꺼짐 — .env 에 SCAN_TG=1 이면 first10·limit_up·jump 를 개인 채팅(TG_CHAT_ID)으로 보냄

  .venv/bin/python scanner.py          # 상시 실행
  .venv/bin/python scanner.py once kr  # 한 번만 (점검용)
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import time
from zoneinfo import ZoneInfo

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bot  # .env 로드, tg()

OUT = os.path.join(bot.STATE_DIR, "scanner")
os.makedirs(OUT, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36"}
KR, NY = ZoneInfo("Asia/Seoul"), ZoneInfo("America/New_York")
JUMP_PP, FADE_PP = 3.0, 5.0


def num(s):
    try:
        return float(str(s).replace(",", ""))
    except (TypeError, ValueError):
        return None


def fetch_kr() -> list[dict]:
    rows = []
    for mkt in ("KOSPI", "KOSDAQ"):
        for page in (1, 2):
            j = requests.get(f"https://m.stock.naver.com/api/stocks/up/{mkt}", params={"page": page, "pageSize": 100},
                             headers=UA, timeout=10).json()
            for it in j.get("stocks", []):
                name = it.get("stockName", "")
                if it.get("stockEndType") != "stock" or "스팩" in name or re.search(r"\d+호$", name):
                    continue
                chg = num(it.get("fluctuationsRatio"))
                if chg is None:
                    continue
                rows.append({"code": it["itemCode"], "name": name, "market": mkt, "price": num(it.get("closePrice")),
                             "chg": chg, "tv": round((num(it.get("accumulatedTradingValue")) or 0) / 100, 1),   # 억원
                             "limit_up": (it.get("compareToPreviousPrice") or {}).get("name") == "UPPER_LIMIT",
                             "pref": not it["itemCode"].endswith("0")})
    return rows


def fetch_us() -> list[dict]:
    j = requests.get("https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved", headers=UA, timeout=10,
                     params={"scrIds": "day_gainers", "count": 100, "formatted": "false"}).json()
    rows = []
    for x in j["finance"]["result"][0]["quotes"]:
        p, mc = x.get("regularMarketPrice") or 0, x.get("marketCap") or 0
        if p < 2 or mc < 3e8:
            continue
        v, av = x.get("regularMarketVolume") or 0, x.get("averageDailyVolume3Month") or 0
        rows.append({"code": x["symbol"], "name": x.get("shortName") or x.get("longName", ""), "market": x.get("fullExchangeName", ""),
                     "price": p, "chg": x.get("regularMarketChangePercent") or 0, "tv": round(p * v / 1e6, 1),   # $백만
                     "vol_ratio": round(v / av, 1) if av else None, "limit_up": False, "pref": False})
    return rows


def session(mkt: str, now_utc: dt.datetime) -> tuple[bool, str, str]:
    if mkt == "kr":
        t = now_utc.astimezone(KR)
        ok = t.weekday() < 5 and (9, 0) <= (t.hour, t.minute) <= (15, 35)
    else:
        t = now_utc.astimezone(NY)
        ok = t.weekday() < 5 and (9, 30) <= (t.hour, t.minute) <= (16, 5)
    return ok, t.strftime("%Y-%m-%d"), t.strftime("%H:%M:%S")


class Tracker:
    """종목별 상태를 들고 있다가 새 스냅샷이 오면 이벤트를 만든다."""

    def __init__(self, mkt: str, day: str):
        self.mkt, self.day = mkt, day
        self.path = os.path.join(OUT, f"{mkt}-{day}.json")
        s = json.load(open(self.path)) if os.path.exists(self.path) else {}
        self.stocks: dict[str, dict] = s.get("stocks", {})
        self.events: list[dict] = s.get("events", [])
        self.polls = s.get("polls", 0)

    def update(self, rows: list[dict], clock: str) -> list[dict]:
        new = []
        seen = set()
        for r in rows:
            c = r["code"]
            seen.add(c)
            st = self.stocks.get(c)
            if st is None:
                st = self.stocks[c] = {"name": r["name"], "market": r["market"], "first_seen": clock, "first10": None,
                                       "limit_up_at": None, "max_chg": r["chg"], "max_at": clock, "faded": False, "pref": r["pref"]}
            prev = st.get("chg")
            st.update(price=r["price"], chg=r["chg"], tv=r["tv"], last=clock, limit_up=r["limit_up"], vol_ratio=r.get("vol_ratio"))
            if r["chg"] > st["max_chg"]:
                st["max_chg"], st["max_at"] = r["chg"], clock
                st["faded"] = False
            ev = None
            if st["first10"] is None and r["chg"] >= 10:
                st["first10"] = clock
                ev = "first10"
            if r["limit_up"] and not st["limit_up_at"]:
                st["limit_up_at"] = clock
                ev = "limit_up"
            elif prev is not None and r["chg"] - prev >= JUMP_PP and r["chg"] >= 5:
                ev = ev or "jump"
            if st["max_chg"] >= 10 and st["max_chg"] - r["chg"] >= FADE_PP and not st["faded"]:
                st["faded"] = True
                ev = ev or "fade"
            if ev and not r["pref"]:
                e = {"t": clock, "type": ev, "code": c, "name": r["name"], "chg": r["chg"], "tv": r["tv"],
                     "prev": prev, "max": st["max_chg"]}
                self.events.append(e)
                new.append(e)
        for c, st in self.stocks.items():          # 순위 밖으로 밀려난 종목 표시
            st["in_list"] = c in seen
        self.polls += 1
        return new

    def save(self, updated: str):
        tmp = self.path + ".tmp"
        json.dump({"market": self.mkt, "day": self.day, "updated": updated, "polls": self.polls,
                   "stocks": self.stocks, "events": self.events[-400:]}, open(tmp, "w"), ensure_ascii=False)
        os.replace(tmp, self.path)

    def log_csv(self, rows: list[dict], clock: str):
        p = os.path.join(OUT, f"{self.mkt}-{self.day}.csv")
        new = not os.path.exists(p)
        with open(p, "a", encoding="utf-8") as f:
            if new:
                f.write("time,code,name,chg,price,tv,limit_up\n")
            for r in rows:
                if r["chg"] >= 5:
                    f.write(f"{clock},{r['code']},{r['name'].replace(',', ' ')},{r['chg']},{r['price']},{r['tv']},{int(r['limit_up'])}\n")


LABEL = {"first10": "🚀 +10% 돌파", "limit_up": "🔺 상한가", "jump": "⚡ 급가속", "fade": "↘️ 고점 반납"}


def alert(mkt: str, events: list[dict]):
    if os.environ.get("SCAN_TG") != "1":
        return
    chat = (os.environ.get("TG_CHAT_ID") or "").strip()
    if chat.startswith("-"):                       # 그룹방 금지
        return
    pick = [e for e in events if e["type"] in ("first10", "limit_up", "jump")][:6]
    if not pick:
        return
    flag = "🇰🇷" if mkt == "kr" else "🇺🇸"
    lines = [f"{flag} {LABEL[e['type']]} <b>{e['name']}</b> {e['chg']:+.1f}%" for e in pick]
    bot.tg("\n".join(lines))


def poll(mkt: str, trackers: dict) -> bool:
    now = dt.datetime.now(dt.timezone.utc)
    ok, day, clock = session(mkt, now)
    if not ok:
        return False
    tr = trackers.get(mkt)
    if tr is None or tr.day != day:
        tr = trackers[mkt] = Tracker(mkt, day)
    rows = fetch_kr() if mkt == "kr" else fetch_us()
    ev = tr.update(rows, clock[:5] if mkt == "us" else clock)
    tr.log_csv(rows, clock)
    tr.save(now.isoformat(timespec="seconds"))
    alert(mkt, ev)
    return True


def main():
    if sys.argv[1:2] == ["once"]:
        mkt = (sys.argv[2:] or ["kr"])[0]
        rows = fetch_kr() if mkt == "kr" else fetch_us()
        print(f"{mkt}: {len(rows)}종목, 1위 {rows[0]['name']} {rows[0]['chg']:+.1f}%" if rows else "없음")
        return
    trackers: dict = {}
    nxt = {"kr": 0.0, "us": 0.0}
    gap = {"kr": 30, "us": 60}
    print("급등 감시 시작", flush=True)
    while True:
        for mkt in ("kr", "us"):
            if time.time() >= nxt[mkt]:
                try:
                    active = poll(mkt, trackers)
                    nxt[mkt] = time.time() + (gap[mkt] if active else 60)
                except Exception as e:
                    bot.log(f"[감시 {mkt}] 오류 {type(e).__name__}: {str(e)[:150]}")
                    nxt[mkt] = time.time() + gap[mkt] * 2
        time.sleep(2)


if __name__ == "__main__":
    main()
