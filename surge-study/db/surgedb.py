"""장중 급등주 SQLite DB — CSV를 한 파일 DB로 묶어 SQL로 바로 조회한다.

원본(진실)은 CSV 그대로다:
  - surge-study/data/intraday/{kr,us}/YYYY-MM-DD.csv  (20분 스냅샷, 수집 봇이 씀)
  - surge-study/db/catalysts.csv                       (재료 판정 캐시, 노트 작성 때 씀)
  - surge-study/db/hypotheses.csv                      (한 줄 가설과 채점)
surge.db 는 이 CSV들로 언제든 다시 만드는 사본이라 git에 올리지 않는다(.gitignore). 빌드는 1초 안쪽.

사용:
  python surge-study/db/surgedb.py build                       # DB 다시 만들기
  python surge-study/db/surgedb.py now us [날짜]               # 최신 스냅샷: 신규 +10%·진행 상황·캐시된 재료
  python surge-study/db/surgedb.py day us [날짜]               # 그날 종목별 요약(첫 +10% 시각·최고·반납)
  python surge-study/db/surgedb.py news us 종목 [날짜]           # 미리 모은 뉴스 제목·공시 전체
  python surge-study/db/surgedb.py sql "SELECT ..."            # 아무 SQL
  python surge-study/db/surgedb.py cat us 날짜 종목 재료 "설명" [출처URL]   # 재료 판정 저장(같은 날·종목이면 덮어씀)
날짜를 빼면 DB에 있는 그 시장의 마지막 날짜.
"""
import csv
import glob
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                       # surge-study/
DB = os.path.join(HERE, "surge.db")
CAT = os.path.join(HERE, "catalysts.csv")
HYP = os.path.join(HERE, "hypotheses.csv")
CAT_COLS = ["market", "date", "symbol", "catalyst", "detail", "source"]
NEWS_COLS = ["symbol", "fetched_at", "auto_cat", "themes", "headlines", "filings", "link"]
HYP_COLS = ["market", "date", "made_at", "text", "result", "graded_at", "note"]

SCHEMA = """
CREATE TABLE snapshots(
  market TEXT, date TEXT, time TEXT, symbol TEXT, name TEXT, exchange TEXT,
  price REAL, chg REAL,
  volume REAL, avg_vol REAL, vol_ratio REAL,   -- 미국: 주식 수 / 한국: NULL
  tv_eok REAL, limit_up INTEGER,               -- 한국: 거래대금(억원)·상한가 / 미국: NULL
  mcap REAL,                                   -- 미국: 달러 / 한국: 억원
  ok INTEGER,                                  -- 분석 대상 필터 통과(미국: $2↑·시총 $3억↑ / 한국: 1)
  PRIMARY KEY(market, date, time, symbol));
CREATE INDEX ix_snap_sym ON snapshots(market, symbol, date);
CREATE TABLE catalysts(market TEXT, date TEXT, symbol TEXT, catalyst TEXT, detail TEXT, source TEXT,
  PRIMARY KEY(market, date, symbol));
CREATE TABLE news(market TEXT, date TEXT, symbol TEXT, fetched_at TEXT, auto_cat TEXT, themes TEXT,
  headlines TEXT, filings TEXT, link TEXT, PRIMARY KEY(market, date, symbol));   -- 수집 봇이 미리 모은 뉴스·공시
CREATE TABLE hypotheses(market TEXT, date TEXT, made_at TEXT, text TEXT, result TEXT, graded_at TEXT, note TEXT);

-- 종목·날짜별 하루 요약 (필터 통과 종목만)
CREATE VIEW daily AS
SELECT s.market, s.date, s.symbol, MAX(s.name) AS name,
  MIN(s.time) AS first_seen,
  MIN(CASE WHEN s.chg >= 10 THEN s.time END) AS first_10,
  MAX(s.chg) AS max_chg,
  (SELECT x.time FROM snapshots x WHERE x.market=s.market AND x.date=s.date AND x.symbol=s.symbol
     ORDER BY x.chg DESC, x.time LIMIT 1) AS max_time,
  (SELECT x.chg FROM snapshots x WHERE x.market=s.market AND x.date=s.date AND x.symbol=s.symbol
     ORDER BY x.time DESC LIMIT 1) AS last_chg,
  MAX(s.time) AS last_seen,
  (SELECT MAX(time) FROM snapshots y WHERE y.market=s.market AND y.date=s.date) AS last_snap,
  COUNT(*) AS n_snaps,
  MAX(s.vol_ratio) AS max_vol_ratio
FROM snapshots s WHERE s.ok = 1 GROUP BY s.market, s.date, s.symbol;

-- 하루 요약 + 반납폭 + 재료
CREATE VIEW daily_full AS
SELECT d.*, ROUND(d.max_chg - CASE WHEN d.last_seen = d.last_snap THEN d.last_chg END, 2) AS giveback,
  (d.last_seen = d.last_snap) AS in_last_snap, c.catalyst, c.detail
FROM daily d LEFT JOIN catalysts c USING(market, date, symbol);
"""


def f(v):
    try:
        return float(v) if v not in ("", None, "nan") else None
    except ValueError:
        return None


def read_csv(path, cols):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return [[r.get(c, "") for c in cols] for r in csv.DictReader(fh)]


def build(quiet=False):
    tmp = DB + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    con = sqlite3.connect(tmp)
    con.executescript(SCHEMA)
    n = 0
    for mkt in ("us", "kr"):
        for p in sorted(glob.glob(os.path.join(ROOT, "data", "intraday", mkt, "20??-??-??.csv"))):
            date = os.path.basename(p)[:10]
            rows = []
            with open(p, newline="", encoding="utf-8") as fh:
                for r in csv.DictReader(fh):
                    if r.get("time") == "time":          # 혹시 섞인 헤더 줄
                        continue
                    price, mcap = f(r.get("price")), f(r.get("mcap") or r.get("mcap_eok"))
                    if mkt == "us":
                        ok = int(price is not None and price >= 2 and mcap is not None and mcap >= 3e8)
                        rows.append((mkt, date, r["time"], r["symbol"], r["name"], r.get("exchange"), price, f(r["chg"]),
                                     f(r.get("volume")), f(r.get("avg_vol_3m")), f(r.get("vol_ratio")), None, None, mcap, ok))
                    else:
                        rows.append((mkt, date, r["time"], r["code"], r["name"], r.get("market"), price, f(r["chg"]),
                                     None, None, None, f(r.get("tv_eok")), int(r.get("limit_up") == "True"), mcap, 1))
            con.executemany("INSERT OR REPLACE INTO snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
            n += len(rows)
    for mkt in ("us", "kr"):
        for p in sorted(glob.glob(os.path.join(ROOT, "data", "intraday", mkt, "news-*.csv"))):
            date = os.path.basename(p)[5:15]
            rows = [[mkt, date] + r for r in read_csv(p, NEWS_COLS)]
            con.executemany("INSERT OR REPLACE INTO news VALUES (?,?,?,?,?,?,?,?,?)", rows)
    con.executemany("INSERT OR REPLACE INTO catalysts VALUES (?,?,?,?,?,?)", read_csv(CAT, CAT_COLS))
    con.executemany("INSERT INTO hypotheses VALUES (?,?,?,?,?,?,?)", read_csv(HYP, HYP_COLS))
    con.commit()
    con.close()
    os.replace(tmp, DB)
    if not quiet:
        print(f"surge.db: 스냅샷 {n}행")


def connect():
    build(quiet=True)                                # CSV가 git pull로 바뀌었을 수 있으니 항상 새로 만든다(빠름)
    return sqlite3.connect(DB)


def show(cur, sql, args=()):
    rows = cur.execute(sql, args).fetchall()
    cols = [d[0] for d in cur.description]
    def fmt(v):
        if isinstance(v, float):
            return f"{v:,.0f}" if abs(v) >= 1e5 else f"{v:.2f}"
        return "" if v is None else str(v)
    print(" | ".join(cols))
    for r in rows:
        print(" | ".join(fmt(v) for v in r))
    return rows


def last_date(cur, mkt):
    return cur.execute("SELECT MAX(date) FROM snapshots WHERE market=?", (mkt,)).fetchone()[0]


def now(mkt, date=None):
    con = connect()
    cur = con.cursor()
    date = date or last_date(cur, mkt)
    times = [t for (t,) in cur.execute("SELECT DISTINCT time FROM snapshots WHERE market=? AND date=? ORDER BY time",
                                       (mkt, date))]
    if not times:
        print(f"{mkt} {date}: 스냅샷 없음"); return
    t = times[-1]
    prev = times[-2] if len(times) > 1 else None
    print(f"# {mkt} {date} 최신 {t} · 오늘 스냅샷 {len(times)}개({', '.join(times)}) · 이전 {prev or '없음'}")
    print("\n## 신규 +10% (이전 스냅샷까지 +10% 없던 종목, 재료 캐시 포함)")
    show(cur, """
      SELECT s.symbol, s.name, s.price, ROUND(s.chg,1) AS chg, s.vol_ratio, ROUND(CASE WHEN s.market='us' THEN s.mcap/1e8 ELSE s.mcap END) AS mcap_eok,  -- 미국 $억 / 한국 원 억
             s.tv_eok,
             c.catalyst, c.detail
      FROM snapshots s LEFT JOIN catalysts c ON c.market=s.market AND c.date=s.date AND c.symbol=s.symbol
      WHERE s.market=? AND s.date=? AND s.time=? AND s.ok=1 AND s.chg>=10
        AND NOT EXISTS (SELECT 1 FROM snapshots p WHERE p.market=s.market AND p.date=s.date AND p.symbol=s.symbol
                        AND p.time<s.time AND p.chg>=10)
      ORDER BY s.chg DESC""", (mkt, date, t))
    if prev:
        print("\n## 진행 상황 (이전에 +10% 찍은 종목: 직전 → 지금, 장중 최고, 반납폭)")
        show(cur, """
          SELECT d.symbol, d.name, d.first_10, ROUND(p.chg,1) AS prev, ROUND(n.chg,1) AS now,
                 ROUND(n.chg-p.chg,1) AS delta, ROUND(d.max_chg,1) AS max, ROUND(d.max_chg-n.chg,1) AS giveback,
                 CASE WHEN n.chg IS NULL THEN '목록 이탈' WHEN n.chg<10 THEN '+10% 이탈' ELSE '' END AS flag, c.catalyst
          FROM daily d
          LEFT JOIN snapshots p ON p.market=d.market AND p.date=d.date AND p.symbol=d.symbol AND p.time=?
          LEFT JOIN snapshots n ON n.market=d.market AND n.date=d.date AND n.symbol=d.symbol AND n.time=?
          LEFT JOIN catalysts c ON c.market=d.market AND c.date=d.date AND c.symbol=d.symbol
          WHERE d.market=? AND d.date=? AND d.first_10 IS NOT NULL AND d.first_10 < ?
          ORDER BY delta""", (prev, t, mkt, date, t))
    print("\n## 재료 판정 안 된 +10% 종목 — 수집 봇이 미리 모은 뉴스·공시 (이걸로 판정, 비었거나 애매할 때만 웹 검색)")
    show(cur, """SELECT s.symbol, s.name, ROUND(s.chg,1) AS chg, n.auto_cat, n.themes, n.filings,
             substr(n.headlines, 1, 400) AS headlines
      FROM snapshots s LEFT JOIN news n ON n.market=s.market AND n.date=s.date AND n.symbol=s.symbol
      WHERE s.market=? AND s.date=? AND s.time=? AND s.ok=1 AND s.chg>=10
        AND NOT EXISTS (SELECT 1 FROM catalysts c WHERE c.market=s.market AND c.date=s.date AND c.symbol=s.symbol)
      ORDER BY s.chg DESC""", (mkt, date, t))


def day(mkt, date=None):
    con = connect()
    cur = con.cursor()
    date = date or last_date(cur, mkt)
    print(f"# {mkt} {date} 하루 요약 (장중 한 번이라도 +10%)")
    show(cur, """SELECT symbol, name, first_10, max_time, ROUND(max_chg,1) max, ROUND(last_chg,1) last, giveback,
                        max_vol_ratio vol, catalyst FROM daily_full
                 WHERE market=? AND date=? AND first_10 IS NOT NULL ORDER BY first_10, max_chg DESC""", (mkt, date))
    print()
    show(cur, """SELECT first_10, COUNT(*) n FROM daily WHERE market=? AND date=? AND first_10 IS NOT NULL
                 GROUP BY first_10 ORDER BY first_10""", (mkt, date))
    print()
    show(cur, """SELECT COUNT(*) AS n_10, SUM(in_last_snap AND last_chg>=10) AS still_10,
                        SUM(giveback>=5) AS giveback_5p FROM daily_full
                 WHERE market=? AND date=? AND first_10 IS NOT NULL""", (mkt, date))


def news_of(mkt, sym, date=None):
    con = connect()
    cur = con.cursor()
    date = date or last_date(cur, mkt)
    for r in cur.execute("SELECT * FROM news WHERE market=? AND date=? AND symbol=?", (mkt, date, sym)):
        print(f"# {sym} {date} (수집 {r[3]}) 자동분류: {r[4] or '-'} · 테마: {r[5] or '-'}")
        print("공시:", r[7] or "-")
        for h in (r[6] or "").split(" || "):
            print(" -", h)
        print("링크:", r[8] or "-")
        return
    print(f"{sym} {date}: 미리 모은 뉴스 없음 → 웹 검색")


def add_catalyst(mkt, date, sym, catalyst, detail="", source=""):
    rows = read_csv(CAT, CAT_COLS)
    rows = [r for r in rows if not (r[0] == mkt and r[1] == date and r[2] == sym)]
    rows.append([mkt, date, sym, catalyst, detail, source])
    rows.sort(key=lambda r: (r[0], r[1], r[2]))
    with open(CAT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(CAT_COLS)
        w.writerows(rows)
    print(f"재료 저장: {mkt} {date} {sym} {catalyst}")


if __name__ == "__main__":
    import signal
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)   # | head 로 잘라 봐도 에러 안 나게
    a = sys.argv[1:]
    cmd = a[0] if a else "build"
    if cmd == "build":
        build()
    elif cmd == "now":
        now(a[1], a[2] if len(a) > 2 else None)
    elif cmd == "day":
        day(a[1], a[2] if len(a) > 2 else None)
    elif cmd == "sql":
        show(connect().cursor(), a[1])
    elif cmd == "news":
        news_of(a[1], a[2], a[3] if len(a) > 3 else None)
    elif cmd == "cat":
        add_catalyst(*a[1:7])
    else:
        print(__doc__)
