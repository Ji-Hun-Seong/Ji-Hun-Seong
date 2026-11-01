"""ETF·지수 일봉(수정주가, 최대 기간) — 나스닥 비교 연구용. 출력 backtest/data/etf_prices.csv.gz"""
import time
import pandas as pd, yfinance as yf
T = ("^NDX ^GSPC ^IXIC ^VIX ^IRX ^TNX QQQ QLD TQQQ SPY SSO UPRO TLT IEF SHY BIL GLD TIP SMH SOXX XLK XLE XLF XLV XLY XLP "
     "XLI XLU XLB XLRE XLC VNQ EFA EEM KRW=X ^KS200 ^KS11 069500.KS 122630.KS 133690.KS 409820.KS 360750.KS").split()
out = []
for t in T:
    for i in range(3):
        try:
            h = yf.Ticker(t).history(period="max", auto_adjust=True)
            if len(h):
                h = h.reset_index()[["Date", "Open", "High", "Low", "Close", "Volume"]]
                h["Date"] = pd.to_datetime(h["Date"]).dt.tz_localize(None).dt.normalize()
                h["code"] = t
                out.append(h)
                print(t, len(h), h.Date.min().date(), h.Date.max().date(), flush=True)
                break
        except Exception as e:
            print("retry", t, e); time.sleep(3)
    time.sleep(0.5)
pd.concat(out).to_csv("backtest/data/etf_prices.csv.gz", index=False)
