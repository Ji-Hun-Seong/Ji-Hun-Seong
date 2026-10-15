"""analyst/fetch.py — 애널리스트 노트용 원자료 수집 (GitHub Actions에서 실행)

20선 + 비교 대상 종목에 대해
  OpenDART : 주요계정(fnlttSinglAcnt) 2014~2025 연간 + 2024~2026 분기, 배당(alotMatter) 10년,
             타법인출자현황(otrCprInvstmntSttus, 지주사 NAV용), 자기주식(tesstkAcqsDspsSttus), 최대주주(hyslrSttus)
  네이버   : integration(시총·PER·PBR·업종비교), finance annual/quarter(컨센서스 포함), 월봉 10년
결과는 analyst_raw/<ticker>.json 하나씩.
"""
import io
import json
import os
import sys
import time
import zipfile
import xml.etree.ElementTree as ET

import requests

DART = "https://opendart.fss.or.kr/api"
UA = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"}
KEY = os.environ.get("DART_API_KEY") or sys.exit("DART_API_KEY 필요")
OUT = sys.argv[1] if len(sys.argv) > 1 else "analyst_raw"
os.makedirs(OUT, exist_ok=True)

HERE = os.path.dirname(os.path.abspath(__file__))
picks = "000270 005440 009970 020000 001800 453340 004490 000320 005720 120115 005740 004170 023530 006650 035250 060980 007860 069260 000810 383800".split()   # 2026-10 가치주 20선
PEERS = """005380 069960 057050 111770 031430 093050 383220 271560 051500 031440 004360 000240
090350 002380 000390 002350 120110 264900 101530 139480 011170 011780 034230 114090 204320
200880 004000 025860 005830 001450 001120 108670 021240 284740 079160 006040 008770 000880""".split()
EXTRA = [t for t in os.environ.get("EXTRA", "").split() if t]
tickers = list(dict.fromkeys(picks + PEERS + EXTRA))


def common(t):
    return t[:-1] + "0" if t[-1] != "0" else t


z = zipfile.ZipFile(io.BytesIO(requests.get(f"{DART}/corpCode.xml", params={"crtfc_key": KEY}, timeout=60).content))
codes = {}
for el in ET.fromstring(z.read(z.namelist()[0])).iter("list"):
    sc = (el.findtext("stock_code") or "").strip()
    if sc:
        codes[sc] = el.findtext("corp_code")


def dart(path, **p):
    for _ in range(3):
        try:
            r = requests.get(f"{DART}/{path}", params={"crtfc_key": KEY, **p}, timeout=30).json()
            time.sleep(0.15)
            return r.get("list") if r.get("status") == "000" else None
        except Exception:
            time.sleep(2)
    return None


def naver(url):
    try:
        return requests.get(url, headers=UA, timeout=20).json()
    except Exception as e:
        return {"error": str(e)}


def monthly(t):
    try:
        txt = requests.get("https://api.finance.naver.com/siseJson.naver",
                           params={"symbol": t, "requestType": 1, "startTime": "20140101",
                                   "endTime": "20261231", "timeframe": "month"}, headers=UA, timeout=20).text
        rows = json.loads(txt.replace("'", '"'))
        return rows
    except Exception as e:
        return {"error": str(e)}


for i, t in enumerate(tickers):
    cc = codes.get(common(t))
    d = {"ticker": t, "corp_code": cc}
    if cc:
        d["annual"] = {y: dart("fnlttSinglAcnt.json", corp_code=cc, bsns_year=str(y), reprt_code="11011")
                       for y in (2025, 2022, 2019, 2016)}
        d["quarter"] = {f"{y}_{rc}": dart("fnlttSinglAcnt.json", corp_code=cc, bsns_year=str(y), reprt_code=rc)
                        for y in (2024, 2025, 2026) for rc in ("11013", "11012", "11014")
                        if not (y == 2026 and rc == "11014")}
        d["dividend"] = {y: dart("alotMatter.json", corp_code=cc, bsns_year=str(y), reprt_code="11011")
                         for y in (2025, 2022, 2019, 2016)}
        d["dividend_h1"] = dart("alotMatter.json", corp_code=cc, bsns_year="2026", reprt_code="11012")
        d["invest"] = dart("otrCprInvstmntSttus.json", corp_code=cc, bsns_year="2025", reprt_code="11011")
        d["invest_h1"] = dart("otrCprInvstmntSttus.json", corp_code=cc, bsns_year="2026", reprt_code="11012")
        d["treasury"] = dart("tesstkAcqsDspsSttus.json", corp_code=cc, bsns_year="2025", reprt_code="11011")
        d["treasury_h1"] = dart("tesstkAcqsDspsSttus.json", corp_code=cc, bsns_year="2026", reprt_code="11012")
        d["holders"] = dart("hyslrSttus.json", corp_code=cc, bsns_year="2026", reprt_code="11012")
        d["shares"] = dart("stockTotqySttus.json", corp_code=cc, bsns_year="2026", reprt_code="11012")
        # 최근 1년 주요 공시 목록(사업 관련)
        d["disclosures"] = dart("list.json", corp_code=cc, bgn_de="20251001", end_de="20261015", page_count="100")
    d["naver"] = naver(f"https://m.stock.naver.com/api/stock/{t}/integration")
    d["fin_annual"] = naver(f"https://m.stock.naver.com/api/stock/{t}/finance/annual")
    d["fin_quarter"] = naver(f"https://m.stock.naver.com/api/stock/{t}/finance/quarter")
    d["monthly"] = monthly(t)
    json.dump(d, open(os.path.join(OUT, f"{t}.json"), "w", encoding="utf-8"), ensure_ascii=False)
    ok = sum(1 for v in (d.get("annual") or {}).values() if v)
    print(f"{i+1}/{len(tickers)} {t} annual={ok}/4 monthly={len(d['monthly']) if isinstance(d['monthly'], list) else 'x'}", flush=True)
