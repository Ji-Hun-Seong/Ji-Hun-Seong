"""일봉 캐시(sqlite) — 코스피 보통주 전 종목 + KOSPI 지수. 첫 실행 약 300봉, 이후 매일 최근 봉만 갱신"""
import datetime as dt, sqlite3, time
import pandas as pd

SCHEMA = """CREATE TABLE IF NOT EXISTS candles(symbol TEXT, d TEXT, o REAL, h REAL, l REAL, c REAL, v REAL, PRIMARY KEY(symbol, d));
CREATE TABLE IF NOT EXISTS meta(symbol TEXT PRIMARY KEY, name TEXT, market TEXT, updated TEXT);"""


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)

    def put(self, symbol, candles):
        rows = []
        for c in candles:
            d = c["timestamp"][:10]
            rows.append((symbol, d, float(c["openPrice"]), float(c["highPrice"]), float(c["lowPrice"]),
                         float(c["closePrice"]), float(c["volume"])))
        self.db.executemany("INSERT OR REPLACE INTO candles VALUES(?,?,?,?,?,?,?)", rows)

    def last_date(self, symbol):
        r = self.db.execute("SELECT MAX(d) FROM candles WHERE symbol=?", (symbol,)).fetchone()
        return r[0]

    def count(self, symbol):
        return self.db.execute("SELECT COUNT(*) FROM candles WHERE symbol=?", (symbol,)).fetchone()[0]

    def panel(self, days=420):
        last = self.db.execute("SELECT MAX(d) FROM candles").fetchone()[0] or dt.date.today().isoformat()
        since = (dt.date.fromisoformat(last) - dt.timedelta(days=int(days * 1.5))).isoformat()
        df = pd.read_sql("SELECT * FROM candles WHERE d>=?", self.db, params=(since,))
        df["d"] = pd.to_datetime(df["d"])
        return {k: df.pivot(index="d", columns="symbol", values=k).sort_index() for k in "ohlcv"}

    def names(self):
        return dict(self.db.execute("SELECT symbol, name FROM meta").fetchall())


def refresh(api, store, log=print, need=300):
    """종목 목록 갱신 후 각 종목 일봉을 채움. 반환: (갱신 종목 수, 실패 목록)"""
    stocks = api.stocks_all("KOSPI") or []
    today = dt.date.today().isoformat()
    store.db.executemany("INSERT OR REPLACE INTO meta VALUES(?,?,?,?)",
                         [(s["symbol"], s["name"], s.get("market"), today) for s in stocks])
    store.db.commit()
    syms = [s["symbol"] for s in stocks] + ["^KOSPI"]
    fail, n = [], 0
    t0 = time.time()
    for i, sym in enumerate(syms):
        try:
            have = store.count(sym)
            get = (lambda **k: api.index_candles("KOSPI", **k)) if sym == "^KOSPI" else (lambda **k: api.candles(sym, **k))
            if have >= need - 20:
                r = get(count=10)                       # 최근 봉만 갱신
                store.put(sym, r.get("candles", []))
            else:
                before, got = None, 0
                while got < need:
                    r = get(count=200, before=before)
                    cs = r.get("candles", [])
                    store.put(sym, cs); got += len(cs)
                    before = r.get("nextBefore")
                    if not before or not cs:
                        break
            n += 1
        except Exception as e:
            fail.append((sym, str(e)[:120]))
        if i % 100 == 0:
            store.db.commit()
            log(f"  일봉 {i}/{len(syms)} ({time.time() - t0:.0f}s)")
    store.db.commit()
    return n, fail
