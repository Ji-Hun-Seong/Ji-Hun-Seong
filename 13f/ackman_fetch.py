"""ackman_fetch.py — 애크먼 '매매일지'(13F 전 분기 이력) + 후보 종목 시세·밸류에이션 수집 (GitHub Actions 전용)
출력: <out>/ackman_13f_history.json, <out>/market.json
"""
import csv, io, json, os, sys, time
import xml.etree.ElementTree as ET
import requests

UA = {"User-Agent": os.environ.get("SEC_UA") or "research bot contact@example.com"}
OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)


def get(url, **kw):
    for i in range(3):
        try:
            time.sleep(0.2)
            r = requests.get(url, headers=kw.pop("headers", UA), timeout=40, **kw)
            r.raise_for_status()
            return r
        except Exception as e:
            err = e
            time.sleep(2)
    raise err


def filings(cik):
    d = get(f"https://data.sec.gov/submissions/CIK{cik}.json").json()
    blocks = [d["filings"]["recent"]]
    for f in d["filings"].get("files", []):
        blocks.append(get(f"https://data.sec.gov/submissions/{f['name']}").json())
    out = {}
    for rec in blocks:
        for form, acc, rd, fd in zip(rec["form"], rec["accessionNumber"], rec["reportDate"], rec["filingDate"]):
            if form in ("13F-HR", "13F-HR/A") and (rd not in out or form == "13F-HR/A"):
                out[rd] = (acc, fd)
    return out


def holdings(cik, acc):
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}"
    items = get(f"{base}/index.json").json()["directory"]["item"]
    xml = next(i["name"] for i in items if i["name"].lower().endswith(".xml") and "primary_doc" not in i["name"].lower())
    root = ET.fromstring(get(f"{base}/{xml}").content)
    ns = {"n": root.tag.split("}")[0].strip("{")}
    out = {}
    for it in root.findall("n:infoTable", ns):
        pc = it.findtext("n:putCall", default="", namespaces=ns).strip()
        key = it.findtext("n:cusip", namespaces=ns) + ("|" + pc if pc else "")
        o = out.setdefault(key, {"name": it.findtext("n:nameOfIssuer", namespaces=ns).strip(), "pc": pc, "value": 0, "shares": 0})
        o["value"] += int(float(it.findtext("n:value", namespaces=ns)))
        o["shares"] += int(float(it.findtext("n:shrsOrPrnAmt/n:sshPrnamt", namespaces=ns)))
    vals = sorted(o["value"] / o["shares"] for o in out.values() if o["shares"] and not o["pc"])
    if vals and vals[len(vals) // 2] < 2:     # 천 달러 단위 신고 보정
        for o in out.values():
            o["value"] *= 1000
    return out


hist = {}
for cik in ("0001336528", "0002026053"):
    for rd, (acc, fd) in sorted(filings(cik).items()):
        if rd in hist:
            continue
        try:
            hist[rd] = {"cik": cik, "acc": acc, "filed": fd, "h": holdings(cik, acc)}
            print("13F", rd, fd, len(hist[rd]["h"]), flush=True)
        except Exception as e:
            print("::warning::13F 실패", rd, str(e)[:100])
json.dump(hist, open(os.path.join(OUT, "ackman_13f_history.json"), "w", encoding="utf-8"), ensure_ascii=False)

# ── 시세·밸류에이션 ──
TICK = "UBER BN MSFT AMZN HHH QSR META V MA SPGI NFLX ICE ALC GOOGL HLT CMG LOW SPY QQQ".split()
market = {}


def stooq(t):
    sym = {"BN": "bn.us", "SPY": "spy.us", "QQQ": "qqq.us"}.get(t, t.lower() + ".us")
    txt = get(f"https://stooq.com/q/d/l/?s={sym}&i=d", headers={"User-Agent": "Mozilla/5.0"}).text
    rows = list(csv.DictReader(io.StringIO(txt)))
    return [(r["Date"], float(r["Close"])) for r in rows if r.get("Close") not in (None, "", "null")]


for t in TICK:
    d = {}
    try:
        px = stooq(t)
        d["px"] = px
        print("px", t, len(px), px[-1] if px else None, flush=True)
    except Exception as e:
        print("::warning::stooq", t, str(e)[:100])
    market[t] = d

try:
    import yfinance as yf
    for t in TICK:
        try:
            info = yf.Ticker(t).info
            keep = ["shortName", "marketCap", "currentPrice", "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "trailingPE", "forwardPE",
                    "pegRatio", "priceToBook", "freeCashflow", "operatingCashflow", "totalDebt", "totalCash", "ebitda",
                    "operatingMargins", "profitMargins", "returnOnEquity", "revenueGrowth", "earningsGrowth", "dividendYield",
                    "enterpriseValue", "trailingEps", "forwardEps", "sector", "industry", "targetMeanPrice", "recommendationMean"]
            market[t]["info"] = {k: info.get(k) for k in keep}
            print("info", t, market[t]["info"].get("forwardPE"), flush=True)
        except Exception as e:
            print("::warning::yf", t, str(e)[:100])
        time.sleep(1)
except Exception as e:
    print("::warning::yfinance 사용 불가", str(e)[:100])
json.dump(market, open(os.path.join(OUT, "market.json"), "w", encoding="utf-8"), ensure_ascii=False)
print("done")
