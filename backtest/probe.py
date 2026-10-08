import requests
UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36"}
for u in ["https://m.stock.naver.com/api/index/KPI200/enrollStocks?page=1&pageSize=20",
          "https://api.stock.naver.com/index/KPI200/enrollStocks?page=1&pageSize=20",
          "https://m.stock.naver.com/api/index/KPI200/integration",
          "https://finance.naver.com/sise/entryJongmok.naver?type=KPI200&page=1",
          "https://finance.naver.com/sise/sise_index.naver?code=KPI200",
          "https://api.finance.naver.com/siseJson.naver?symbol=005930&requestType=1&startTime=20260901&endTime=20261008&timeframe=day",
          "https://api.finance.naver.com/siseJson.naver?symbol=KPI200&requestType=1&startTime=20260901&endTime=20261008&timeframe=day"]:
    try:
        r=requests.get(u,headers=UA,timeout=20)
        t=r.content.decode("utf-8","ignore")
        i=t.find("itemCode"); i=t.find("code=") if i<0 else i
        print("==",u,"\n",r.status_code,len(t),repr(t[max(0,i-100):i+400] if i>=0 else t[:400]))
    except Exception as e: print("==",u,e)
