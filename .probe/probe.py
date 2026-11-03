import json, os, re, requests
UA = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1"}
def show(name, url, **kw):
    try:
        r = requests.get(url, headers=UA, timeout=20, **kw)
        t = r.text
        print(f"\n===== {name} [{r.status_code}] {len(t)}B")
        try:
            print(json.dumps(r.json(), ensure_ascii=False)[:3500])
        except Exception:
            print(t[:1500])
        return r
    except Exception as e:
        print(f"\n===== {name} ERR {e}")
c = "005930"
show("integration", f"https://m.stock.naver.com/api/stock/{c}/integration")
show("basic", f"https://m.stock.naver.com/api/stock/{c}/basic")
show("trend", f"https://m.stock.naver.com/api/stock/{c}/trend", params={"pageSize": 30})
show("fin-annual", f"https://m.stock.naver.com/api/stock/{c}/finance/annual")
show("fin-quarter", f"https://m.stock.naver.com/api/stock/{c}/finance/quarter")
r = requests.get(f"https://finance.naver.com/item/frgn.naver?code={c}&page=1", headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
r.encoding = "euc-kr"; t = r.text; i = t.find("외국인ㆍ기관 순매매 거래량")
print("\n===== frgn html", r.status_code, len(t), i); print(re.sub(r"\s+", " ", t[i:i+3000]))
show("yahoo US", "https://query1.finance.yahoo.com/v8/finance/chart/AAPL", params={"range": "5d", "interval": "1d"})
k = os.environ.get("DART_API_KEY")
if k:
    show("dart fnltt", "https://opendart.fss.or.kr/api/fnlttSinglAcnt.json", params={"crtfc_key": k, "corp_code": "00126380", "bsns_year": "2025", "reprt_code": "11011"})
    show("dart list", "https://opendart.fss.or.kr/api/list.json", params={"crtfc_key": k, "corp_code": "00126380", "bgn_de": "20260801", "page_count": 5})
try:
    import yfinance as yf
    t = yf.Ticker("AAPL"); info = t.info
    print("\n===== yf info keys", {k: info.get(k) for k in ["shortName","marketCap","trailingPE","forwardPE","priceToBook","dividendYield","heldPercentInstitutions","heldPercentInsiders","shortPercentOfFloat","sector","industry","targetMeanPrice","recommendationKey","fiftyTwoWeekHigh","fiftyTwoWeekLow","returnOnEquity","debtToEquity","operatingMargins","profitMargins","revenueGrowth"]})
    print(t.income_stmt.index.tolist()[:40]); print(t.income_stmt.columns.tolist())
    print(t.quarterly_income_stmt.columns.tolist()); print(t.balance_sheet.index.tolist()[:40])
    print(t.institutional_holders.head() if t.institutional_holders is not None else None)
except Exception as e:
    print("yf ERR", e)
