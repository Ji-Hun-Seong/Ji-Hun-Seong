"""fetch_data.py — 코스피200 현재 구성종목 + 코스피200 지수 일봉을 받아 backtest/data/ 에 저장."""
import os
import time

import pandas as pd

from backtest import kospi200_codes, prices

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "data")
os.makedirs(D, exist_ok=True)

k200 = kospi200_codes()
pd.Series(k200, name="name").rename_axis("code").to_csv(os.path.join(D, "k200_members.csv"), encoding="utf-8-sig")
frames = []
for c in list(k200) + ["KPI200"]:
    try:
        df = prices(c, "2014-01-01")
        frames.append(df.assign(code=c))
    except Exception as e:
        print("skip", c, e)
    time.sleep(0.12)
allp = pd.concat(frames).reset_index().rename(columns={"index": "Date"})
allp.to_csv(os.path.join(D, "k200_prices.csv.gz"), index=False, compression="gzip", float_format="%.4f")
print(len(frames), "series", len(allp), "rows")
