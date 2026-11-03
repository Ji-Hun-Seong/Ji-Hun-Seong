import json, requests
UA = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1"}
g = lambda u, **p: requests.get(u, headers=UA, params=p, timeout=20)
r = g("https://m.stock.naver.com/api/stock/021240/trend", pageSize=60).json()
print("trend60", len(r), r[-1]["bizdate"] if r else None)
r2 = g("https://m.stock.naver.com/api/stock/021240/trend", pageSize=30, bizdate=r[-1]["bizdate"]).json() if r else []
print("trend page2", len(r2), r2[0]["bizdate"] if r2 else None, r2[-1]["bizdate"] if r2 else None)
j = g("https://m.stock.naver.com/api/stock/021240/integration").json()
print("keys", list(j.keys()))
for k in ("consensusInfo", "researches", "industryCode", "description"):
    print(k, json.dumps(j.get(k), ensure_ascii=False)[:800])
print(json.dumps([x["code"] for x in j["totalInfos"]]))
r = g("https://api.finance.naver.com/siseJson.naver", symbol="021240", requestType=1, timeframe="day", startTime="20241101", endTime="20261103")
print("sise", r.status_code, r.text[:300], r.text.count("\n"))
