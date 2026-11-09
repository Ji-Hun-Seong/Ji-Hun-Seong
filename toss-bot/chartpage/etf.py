"""📦 ETF 수익률 순위 — KRX Open API 'ETF 일별매매정보'를 매일 모아 수익률로 줄 세운다.

  · 데이터: KRX Open API (openapi.krx.co.kr) etf_bydd_trd — 하루 1번 호출에 그날 전 ETF
            (종가·NAV·순자산총액·거래대금·기초지수). 키는 서버 .env 의 KRX_API_KEY (GitHub에 올리지 않음)
  · 저장: state/etf.db (SQLite) — 처음엔 3년치를 최근 날짜부터 거꾸로 받음(하루 1호출, 약 780번 · 몇 분)
           이후 매시간 빠진 날만 채움. KRX는 전 거래일 데이터를 다음 날 아침에 올림
  · 순위: 모멘텀 = 3·6·12개월 수익률 평균 · 순자산 200억↑ · 상장 1년↑ · 같은 기초지수끼리는 1년 수익 1등만
  · 수익률은 '가격 기준'(분배금 제외) — 배당·채권형은 실제 총수익보다 낮게 나옴
  · 검증: 과거 매달 그 시점 상위 10개를 샀다면 다음 3개월에 KODEX 200을 이긴 비율

사용:  python chartpage/etf.py fetch 20261105   # 하루 받아 보기(연결 확인)
       python chartpage/etf.py backfill         # 빠진 날 채우기(포그라운드)
       python chartpage/etf.py show             # 순위 상위 출력
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(HERE, "state", "etf.db")
URL = "https://data-dbg.krx.co.kr/svc/apis/etp/etf_bydd_trd"
YEARS_BACK = 1130                       # 달력일 — 3년 수익률 + 여유
MIN_NET = 2e10                          # 순자산 200억원
H = {"r1": 21, "r3": 63, "r6": 126, "r12": 252, "r36": 756}   # 거래일
BENCH = {"069500": "KODEX 200", "360750": "TIGER 미국S&P500"}
STATUS = {"state": "starting", "msg": "", "done": 0, "todo": 0, "at": None}
_db_lock = threading.Lock()


def _load_env():
    p = os.path.join(HERE, ".env")
    if os.path.exists(p):
        for ln in open(p, encoding="utf-8"):
            if "=" in ln and not ln.lstrip().startswith("#"):
                k, v = ln.split("=", 1)
                os.environ.setdefault(k.strip(), v.split(" #")[0].strip().strip('"').strip("'"))


def _key():
    _load_env()
    return os.environ.get("KRX_API_KEY", "").strip()


def kst_today():
    return (dt.datetime.utcnow() + dt.timedelta(hours=9)).date()


def _conn():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB, timeout=30)
    c.execute("""CREATE TABLE IF NOT EXISTS px(d TEXT, code TEXT, name TEXT, close REAL, nav REAL, net REAL,
                 tv REAL, idx TEXT, PRIMARY KEY(d, code))""")
    c.execute("CREATE TABLE IF NOT EXISTS days(d TEXT PRIMARY KEY, n INTEGER, at TEXT)")
    return c


def _f(x):
    if x is None:
        return None
    s = str(x).replace(",", "").strip()
    if s in ("", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _code(r):
    c = str(r.get("ISU_CD") or r.get("ISU_SRT_CD") or "").strip()
    if len(c) == 12 and c.startswith("KR"):          # ISIN(KR7069500007) → 단축코드
        c = c[3:9]
    return c


class KrxError(Exception):
    pass


def fetch_day(d: str) -> list[dict]:
    """d = YYYYMMDD. 휴장일·미게시일은 빈 목록."""
    key = _key()
    if not key:
        raise KrxError("서버 .env 에 KRX_API_KEY 가 없어요")
    req = urllib.request.Request(f"{URL}?basDd={d}", headers={"AUTH_KEY": key, "User-Agent": "toss-bot-etf"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", "replace")[:200]
        raise KrxError(f"KRX {e.code}: {msg}") from None
    try:
        j = json.loads(body)
    except ValueError:
        raise KrxError(f"KRX 응답이 JSON이 아님: {body[:160]}") from None
    if isinstance(j, dict) and "OutBlock_1" in j:
        return j["OutBlock_1"] or []
    raise KrxError(f"KRX 응답: {str(j)[:200]}")


def save_day(c, d: str, rows: list[dict]):
    iso = f"{d[:4]}-{d[4:6]}-{d[6:]}"
    vals = []
    for r in rows:
        code = _code(r)
        if not code:
            continue
        vals.append((iso, code, (r.get("ISU_NM") or r.get("ISU_ABBRV") or "").strip(), _f(r.get("TDD_CLSPRC")),
                     _f(r.get("NAV")), _f(r.get("INVSTASST_NETASST_TOTAMT")), _f(r.get("ACC_TRDVAL")),
                     (r.get("IDX_IND_NM") or "").strip()))
    with _db_lock:
        c.executemany("INSERT OR REPLACE INTO px VALUES(?,?,?,?,?,?,?,?)", vals)
        c.execute("INSERT OR REPLACE INTO days VALUES(?,?,?)", (iso, len(vals), dt.datetime.utcnow().isoformat()))
        c.commit()
    return len(vals)


def _todo(c):
    t = kst_today()
    have = dict(c.execute("SELECT d, n FROM days").fetchall())
    out = []
    for i in range(0, YEARS_BACK):
        day = t - dt.timedelta(days=i)
        if day.weekday() >= 5:
            continue
        iso = day.isoformat()
        if iso not in have or (have[iso] == 0 and i <= 4):   # 최근 며칠은 '아직 안 올라옴'일 수 있어 다시 확인
            out.append(day.strftime("%Y%m%d"))
    return out


def backfill(verbose=False):
    c = _conn()
    todo = _todo(c)
    STATUS.update(state="fetching" if todo else "ok", todo=len(todo), done=0, msg="")
    fails = 0
    for d in todo:
        try:
            n = save_day(c, d, fetch_day(d))
            fails = 0
            STATUS["done"] += 1
            if verbose:
                print(d, n, flush=True)
        except KrxError as e:
            STATUS.update(state="error", msg=str(e))
            if verbose:
                print(d, e, flush=True)
            c.close()
            return False
        except Exception as e:                    # 네트워크 일시 오류
            fails += 1
            STATUS["msg"] = f"{type(e).__name__}: {str(e)[:120]}"
            if fails >= 5:
                STATUS["state"] = "error"
                c.close()
                return False
            time.sleep(3)
        time.sleep(0.12)
    STATUS.update(state="ok", at=dt.datetime.utcnow().isoformat())
    c.close()
    return True


def worker():
    """대시보드가 켜질 때 뒤에서 계속: 빠진 날 채우기 → 1시간 쉬기 (오류면 30분 뒤 다시)"""
    while True:
        try:
            ok = backfill()
        except Exception as e:
            STATUS.update(state="error", msg=f"{type(e).__name__}: {str(e)[:160]}")
            ok = False
        time.sleep(3600 if ok else 1800)


# ── 분류 (이름 기준) ─────────────────────────────────────────────
LEV = re.compile(r"레버리지|인버스|2X|곱버스|선물인버스", re.I)
BOND = re.compile(r"채권|국채|국고|금리|CD|KOFR|SOFR|머니마켓|단기|회사채|크레딧|통안|은행채|특수채|국공채|TDF|TRF|혼합|채권혼합|물가채|하이일드|MMF", re.I)
CMDTY = re.compile(r"골드|금현물|금선물|금은|은선물|원유|WTI|구리|원자재|천연가스|농산물|금속")
FOREIGN = re.compile(r"미국|S&P|나스닥|NASDAQ|다우|필라델피아|차이나|중국|항셍|홍콩|일본|니케이|인도|베트남|유로|유럽|독일|글로벌|"
                     r"선진국|신흥국|대만|라틴|브라질|MSCI|월드|World|빅테크|테슬라|엔비디아|애플|마이크로소프트|아마존|구글|TSMC", re.I)


def classify(name: str) -> str:
    if LEV.search(name):
        return "lev"
    if CMDTY.search(name):
        return "cmdty"
    if BOND.search(name):
        return "bond"
    if FOREIGN.search(name):
        return "foreign"
    return "kr"


def pension(name: str, cat: str) -> str:
    """퇴직연금(DC·IRP) 담을 수 있는 한도 — 이름으로 추정. "100" 적립금 전부 가능 · "70" 위험자산 한도 안에서 · "no" 담을 수 없음
       100 = 적격 TDF · 채권혼합(주식 50% 이하) · 채권형·금리형 / 70 = 주식형·주식혼합·원자재 현물 등 / no = 레버리지·인버스·합성·선물(파생형)"""
    n = name.upper()
    if "합성" in n and cat != "lev" and re.search(r"금리|CD|KOFR|SOFR", n):      # CD·KOFR 금리형은 스왑(합성)이어도 안전자산으로 담음
        return "100"
    if cat == "lev" or "합성" in n:
        return "no"
    if "TDF" in n:
        return "100" if "적격" in n else "70"
    m = re.search(r"TRF\s*(\d{2})(\d{2})", n)
    if m:
        return "100" if int(m.group(1)) <= 50 else "70"
    if re.search(r"채혼합|채권혼합", n):
        return "100"
    if "선물" in n:
        return "no"
    if "주식혼합" in n or "하이일드" in n:
        return "70"
    return "100" if cat == "bond" else "70"


CAT_LABEL = {"kr": "국내주식", "foreign": "해외주식", "bond": "채권·혼합", "cmdty": "원자재", "lev": "레버리지·인버스"}


def _rnd(x, n=1):
    return None if x is None or x != x else round(float(x), n)


def summary():
    import numpy as np
    import pandas as pd
    c = _conn()
    days = pd.read_sql("SELECT d FROM days WHERE n > 0 ORDER BY d", c)["d"].tolist()
    base = {"kind": "etf", "status": dict(STATUS), "hist_days": len(days), "has_key": bool(_key())}
    if not days:
        c.close()
        return {**base, "items": [], "empty": True}
    cut = days[max(0, len(days) - 800)]
    px = pd.read_sql("SELECT d, code, name, close, nav, net, tv, idx FROM px WHERE d >= ?", c, params=(cut,))
    c.close()
    px = px[px.d.isin(days)]
    close = px.pivot(index="d", columns="code", values="close").sort_index()
    net = px.pivot(index="d", columns="code", values="net").sort_index()
    L = close.index[-1]
    last = px[px.d == L].set_index("code")
    n = len(close)

    def ret(col, h, at=None):
        at = n - 1 if at is None else at
        if at - h < 0:
            return None
        a, b = close.iloc[at - h][col], close.iloc[at][col]
        if a != a or b != b or not a:
            return None
        return (b / a - 1) * 100

    rets = {k: {} for k in H}
    for k, h in H.items():
        if n - 1 - h >= 0:
            r = (close.iloc[-1] / close.iloc[n - 1 - h] - 1) * 100
            rets[k] = r.to_dict()
    tail = close.iloc[-253:] if n >= 60 else close
    dr = tail.pct_change(fill_method=None)
    vol = (dr.std() * np.sqrt(252) * 100).to_dict()
    mdd = ((tail / tail.cummax() - 1).min() * 100).to_dict()

    items = []
    for code, row in last.iterrows():
        name = row["name"] or code
        g = lambda k: rets[k].get(code) if rets[k] else None
        r1, r3, r6, r12, r36 = (_rnd(g(k)) for k in ("r1", "r3", "r6", "r12", "r36"))
        moms = [x for x in (r3, r6, r12) if x is not None]
        it = {"code": code, "name": name, "cat": classify(name), "active": "액티브" in name,
              "hedge": "(H)" in name, "synth": "합성" in name, "idx": row["idx"] or "",
              "net_eok": _rnd((row["net"] or 0) / 1e8, 0), "tv_eok": _rnd((row["tv"] or 0) / 1e8, 1),
              "close": row["close"], "nav": row["nav"],
              "disc": _rnd((row["close"] / row["nav"] - 1) * 100, 2) if row["nav"] and row["close"] else None,
              "r1": r1, "r3": r3, "r6": r6, "r12": r12, "r36": r36,
              "mom": _rnd(sum(moms) / len(moms)) if len(moms) == 3 or (n < 253 and moms) else None,
              "vol": _rnd(vol.get(code)), "mdd": _rnd(mdd.get(code)),
              "young": bool(n >= 253 and close[code].iloc[-253] != close[code].iloc[-253])}
        it["eff"] = _rnd(r12 / it["vol"], 2) if r12 is not None and it["vol"] else None
        items.append(it)

    bench = {}
    for code, nm in BENCH.items():
        if code in close.columns:
            bench[code] = {"name": nm, **{k: _rnd(rets[k].get(code)) if rets[k] else None for k in H}}
    k200 = bench.get("069500", {})

    # 거르기: 순자산 200억↑ · 상장 1년↑(데이터가 1년 넘게 쌓였을 때만) · 모멘텀 계산 가능
    ok = [x for x in items if (x["net_eok"] or 0) >= MIN_NET / 1e8 and not x["young"] and x["mom"] is not None]
    for x in ok:
        x["pen"] = pension(x["name"], x["cat"])
        x["ex12"] = _rnd(x["r12"] - k200["r12"]) if x["r12"] is not None and k200.get("r12") is not None else None
    # 같은 기초지수끼리 묶기 — 1년(없으면 모멘텀) 수익 1등만 대표, 나머지 개수 표시
    grp = {}
    for x in ok:
        key = (x["idx"] or x["code"]) + ("|H" if x["hedge"] else "") + ("|A" if x["active"] else "")
        grp.setdefault(key, []).append(x)
    reps = []
    for g in grp.values():
        g.sort(key=lambda x: -(x["r12"] if x["r12"] is not None else x["mom"]))
        g[0]["sibs"] = len(g) - 1
        g[0]["sib_names"] = [y["name"] for y in g[1:4]]
        reps.append(g[0])
    reps.sort(key=lambda x: -x["mom"])

    out = {**base, "asof": L, "n_all": len(items), "n_ok": len(ok), "items": reps, "more": [x for x in ok if x not in reps], "bench": bench,
           "cats": CAT_LABEL, "bt": _backtest(close, net, last) if n >= 253 + 63 else None}
    return out


def _backtest(close, net, last):
    """과거 매달(21거래일마다) 그 시점 모멘텀 상위 10개(레버리지·인버스 제외, 같은 지수 1개) → 다음 3개월 vs KODEX 200"""
    import numpy as np
    n = len(close)
    if "069500" not in close.columns:
        return None
    cat = {c: classify(str(last["name"].get(c, ""))) for c in close.columns}
    idx = last["idx"].to_dict()
    res = []
    for t in range(252, n - 63, 21):
        c0 = close.iloc[t]
        moms = sum((c0 / close.iloc[t - h] - 1) for h in (63, 126, 252)) / 3
        ok = moms[(net.iloc[t] >= MIN_NET) & close.iloc[t - 252].notna() & moms.notna()]
        ok = ok[[cat.get(c) != "lev" for c in ok.index]].sort_values(ascending=False)
        pick, seen = [], set()
        for c in ok.index:
            k = idx.get(c) or c
            if k in seen:
                continue
            seen.add(k)
            pick.append(c)
            if len(pick) == 10:
                break
        if len(pick) < 5:
            continue
        fwd = (close.iloc[t + 63][pick] / c0[pick] - 1).mean() * 100
        b = (close.iloc[t + 63]["069500"] / c0["069500"] - 1) * 100
        if fwd == fwd and b == b:
            res.append((close.index[t], float(fwd), float(b)))
    if not res:
        return None
    wins = sum(1 for _, a, b in res if a > b)
    return {"n": len(res), "wins": wins, "avg_top": round(float(np.mean([a for _, a, _ in res])), 1),
            "avg_bench": round(float(np.mean([b for _, _, b in res])), 1), "from": res[0][0], "to": res[-1][0]}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "show"
    if cmd == "fetch":
        d = sys.argv[2] if len(sys.argv) > 2 else (kst_today() - dt.timedelta(days=1)).strftime("%Y%m%d")
        rows = fetch_day(d)
        print(d, len(rows), "개")
        for r in rows[:3]:
            print(json.dumps(r, ensure_ascii=False))
    elif cmd == "backfill":
        print("완료" if backfill(verbose=True) else f"중단: {STATUS['msg']}")
    else:
        s = summary()
        print(s.get("asof"), "전체", s.get("n_all"), "통과", s.get("n_ok"), "보관 거래일", s.get("hist_days"))
        print("검증", s.get("bt"))
        for i, x in enumerate(s["items"][:20], 1):
            print(i, x["code"], x["name"], CAT_LABEL[x["cat"]], "모멘텀", x["mom"], "1년", x["r12"], "3년", x["r36"])
