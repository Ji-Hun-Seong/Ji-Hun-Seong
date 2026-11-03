"""데이터 소스 응답 점검용 (수동 실행)"""
import json, requests
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36"}
def show(name, url, **kw):
    try:
        r = requests.get(url, headers=UA, timeout=20, **kw)
        print(f"== {name} {r.status_code}\n{r.text[:900]}\n")
    except Exception as e:
        print(f"== {name} ERR {e}\n")
show("naver listing", "https://m.stock.naver.com/api/stocks/marketValue/KOSDAQ", params={"page": 1, "pageSize": 2})
show("naver up", "https://m.stock.naver.com/api/stocks/up/KOSDAQ", params={"page": 1, "pageSize": 3})
show("yahoo gainers", "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved", params={"scrIds": "day_gainers", "count": 3})
show("yahoo gainers2", "https://query2.finance.yahoo.com/v1/finance/screener/predefined/saved", params={"scrIds": "day_gainers", "count": 3, "formatted": "false"})
show("yahoo chart", "https://query1.finance.yahoo.com/v8/finance/chart/AAPL", params={"range": "5d", "interval": "1d"})
show("nasdaq gainers", "https://api.nasdaq.com/api/marketmovers", params={"assetclass": "stocks"})
