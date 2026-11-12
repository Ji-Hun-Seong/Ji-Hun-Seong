"""fetch_us_events.py — 미국 '좋은 공시' 백테스트용 이벤트 (README 9차)
  us_earn8k.csv.gz : SEC EDGAR 8-K Item 2.02(실적 발표) 접수 시각 — 종목별 실적 발표일 (무료·실시간, 봇 실매매에도 같은 소스)
  us_yfearn.csv.gz : yfinance 실적일 + EPS 예상/실제/서프라이즈(%) (받아지는 만큼)
  us_div.csv.gz    : 배당 이력(배당락일, 주당 배당금) — 배당 증액 판단
대상: bt-data-us 의 us_prices 에 가격이 있는 종목.
"""
import io, os, subprocess, sys, time
import pandas as pd, requests

HERE = os.path.dirname(os.path.abspath(__file__)); D = os.path.join(HERE, "data"); os.makedirs(D, exist_ok=True)
UA = {"User-Agent": "Ji-Hun-Seong backtest backtest-bot@users.noreply.github.com", "Accept-Encoding": "gzip, deflate"}
subprocess.run(["git", "fetch", "-q", "--depth", "1", "origin", "bt-data-us"], check=True)
raw = subprocess.run(["git", "show", "FETCH_HEAD:us_prices.csv.gz"], capture_output=True, check=True).stdout
tick = sorted(pd.read_csv(io.BytesIO(raw), compression="gzip", usecols=["code"]).code.unique())
tick = [t for t in tick if t != "SPY"]
print("종목", len(tick))


def sec(url):
    for k in range(4):
        try:
            r = requests.get(url, headers=UA, timeout=30)
            if r.status_code == 200:
                return r.json()
            print("sec", r.status_code, url); time.sleep(2 + 3 * k)
        except Exception as e:
            print("retry", e); time.sleep(2)
    return None


ct = sec("https://www.sec.gov/files/company_tickers.json") or {}
cik = {v["ticker"].replace(".", "-"): int(v["cik_str"]) for v in ct.values()}
rows = []
for n, t in enumerate(tick):
    c = cik.get(t)
    if not c:
        continue
    j = sec(f"https://data.sec.gov/submissions/CIK{c:010d}.json")
    if not j:
        continue
    parts = [j["filings"]["recent"]] + [sec(f"https://data.sec.gov/submissions/{f['name']}") or {} for f in j["filings"].get("files", [])
                                         if f.get("filingTo", "9999") >= "2013-06-01"]
    for p in parts:
        for form, fd, acc, items in zip(p.get("form", []), p.get("filingDate", []), p.get("acceptanceDateTime", []), p.get("items", [])):
            if form == "8-K" and "2.02" in (items or "") and fd >= "2013-06-01":
                rows.append((t, fd, acc, items))
        time.sleep(0.12)
    time.sleep(0.12)
    if n % 50 == 0:
        print("edgar", n, t, len(rows), flush=True)
pd.DataFrame(rows, columns=["code", "filed", "accepted", "items"]).to_csv(os.path.join(D, "us_earn8k.csv.gz"), index=False)
print("8-K 2.02", len(rows), "CIK 없음", sum(1 for t in tick if t not in cik))

import yfinance as yf
divs, earn, fail = [], [], 0
for n, t in enumerate(tick):
    try:
        tk = yf.Ticker(t)
        d = tk.dividends
        if d is not None and len(d):
            divs += [(t, str(i.date()), float(v)) for i, v in d.items()]
    except Exception as e:
        print("div fail", t, e)
    try:
        e = tk.get_earnings_dates(limit=60)
        if e is not None and len(e):
            e = e.reset_index(); e.columns = ["dt", "est", "act", "surp"] + list(e.columns[4:])
            earn += [(t, str(r.dt), r.est, r.act, r.surp) for r in e.itertuples()]
    except Exception as ex:
        fail += 1
        if fail < 10:
            print("earn fail", t, ex)
    time.sleep(0.3)
    if n % 50 == 0:
        print("yf", n, t, len(divs), len(earn), "fail", fail, flush=True)
pd.DataFrame(divs, columns=["code", "exdate", "div"]).to_csv(os.path.join(D, "us_div.csv.gz"), index=False)
pd.DataFrame(earn, columns=["code", "dt", "est", "act", "surp"]).to_csv(os.path.join(D, "us_yfearn.csv.gz"), index=False)
print("완료 배당", len(divs), "yf 실적", len(earn), "실패", fail)
