"""fetch_dart.py — 코스피 상장사의 DART 공시(2014~)를 받아 backtest/data/ 에 저장한다.

  dart_filings.csv.gz : 주요사항보고(B)·거래소공시(I) 목록 (rcept_dt, stock_code, report_nm, rcept_no, flr_nm)
  dart_insider.csv.gz : 임원·주요주주 특정증권 소유상황 보고(증감 수량·비율)

필요: DART_API_KEY (https://opendart.fss.or.kr 무료 발급)
"""
import io
import os
import sys
import time
import zipfile
import xml.etree.ElementTree as ET
from datetime import date

import pandas as pd
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "data")
os.makedirs(D, exist_ok=True)
API = "https://opendart.fss.or.kr/api"
KEY = (os.environ.get("DART_API_KEY") or "").strip()
if not KEY:
    print("DART_API_KEY_MISSING")
    sys.exit(2)
print("DART_API_KEY 길이", len(KEY))
UA = {"User-Agent": "Mozilla/5.0"}
calls = 0


def get(path, **params):
    global calls
    for attempt in range(4):
        try:
            calls += 1
            r = requests.get(f"{API}/{path}", params={"crtfc_key": KEY, **params}, timeout=30)
            j = r.json()
            if j.get("status") == "020":           # 요청 제한 초과
                print("rate limit", calls); time.sleep(30); continue
            return j
        except Exception as e:
            print("retry", path, e); time.sleep(2 + attempt)
    return {}


# 종목코드 → 고유번호
z = zipfile.ZipFile(io.BytesIO(requests.get(f"{API}/corpCode.xml", params={"crtfc_key": KEY}, timeout=60).content))
root = ET.fromstring(z.read(z.namelist()[0]))
s2c = {}
for el in root.iter("list"):
    sc = (el.findtext("stock_code") or "").strip()
    if sc:
        s2c[sc] = el.findtext("corp_code")
print("상장사 고유번호", len(s2c))

# 대상: 코스피 보통주(네이버 목록)
codes = []
for page in range(1, 40):
    j = requests.get("https://m.stock.naver.com/api/stocks/marketValue/KOSPI",
                     params={"page": page, "pageSize": 100}, headers=UA, timeout=20).json()
    items = j.get("stocks", []) if isinstance(j, dict) else j
    if not items:
        break
    codes += [it["itemCode"] for it in items if it.get("stockEndType") == "stock" and it["itemCode"].endswith("0")]
codes = [c for c in codes if c in s2c]
if os.environ.get("DART_LIMIT"):
    codes = codes[: int(os.environ["DART_LIMIT"])]
print("대상 종목", len(codes))

end = date.today().strftime("%Y%m%d")
fil, ins = [], []
for i, sc in enumerate(codes):
    cc = s2c[sc]
    for ty in ("B", "I"):
        page = 1
        while True:
            j = get("list.json", corp_code=cc, bgn_de="20140101", end_de=end, pblntf_ty=ty,
                    page_no=page, page_count=100)
            if j.get("status") != "000":
                break
            for it in j.get("list", []):
                fil.append((it["rcept_dt"], sc, ty, it["report_nm"].strip(), it["rcept_no"], it.get("flr_nm", "")))
            if page >= int(j.get("total_page", 1)):
                break
            page += 1
            time.sleep(0.05)
        time.sleep(0.05)
    j = get("elestock.json", corp_code=cc)
    for it in j.get("list", []) if j.get("status") == "000" else []:
        ins.append((it.get("rcept_dt"), sc, it.get("repror"), it.get("isu_exctv_ofcps"), it.get("isu_main_shrholdr"),
                    it.get("sp_stock_lmp_irds_cnt"), it.get("sp_stock_lmp_irds_rate"), it.get("sp_stock_lmp_rate"), it.get("rcept_no")))
    time.sleep(0.05)
    if i % 50 == 0:
        print(i, len(fil), len(ins), "calls", calls, flush=True)

pd.DataFrame(fil, columns=["rcept_dt", "code", "ty", "report_nm", "rcept_no", "flr_nm"]).to_csv(
    os.path.join(D, "dart_filings.csv.gz"), index=False, compression="gzip")
pd.DataFrame(ins, columns=["rcept_dt", "code", "repror", "ofcps", "main_shrholdr", "irds_cnt", "irds_rate", "rate", "rcept_no"]).to_csv(
    os.path.join(D, "dart_insider.csv.gz"), index=False, compression="gzip")
print("완료 filings", len(fil), "insider", len(ins), "calls", calls)
