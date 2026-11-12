"""fetch_bb_detail.py — 자사주 공시 '질' 백테스트용 상세 데이터 (README 8차 2단계)

bt-data-dart 의 공시 목록(dart_filings.csv.gz)을 받아서, 자사주 취득결정·신탁계약 원공시마다
  amount     : 취득 예정 금액(원) — 신탁은 계약금액, 직접취득은 취득예정금액(없으면 주식수×전일 종가는 분석 때)
  shares_plan: 취득 예정 주식수(보통주)
  burn       : 취득 목적에 '소각'이 들어있는지
  shares     : 공시 시점에 이미 나와 있던 최근 사업보고서의 발행주식총수(보통주) → 시가총액 계산
  equity     : 같은 사업보고서의 자본총계(연결 우선, 지배기업 소유주지분 있으면 그것) → PBR 계산
그리고 기업가치제고계획(밸류업) 원공시마다 pledge_year(연간 자사주 매입 약속액, 원)
→ backtest/data/bb_detail.csv.gz, bb_valueup.csv.gz  (워크플로가 bt-data-bb 브랜치로 올림)

사업보고서는 3월 말에 나오므로 공시 월이 1~3월이면 전전년도, 4월 이후면 전년도 사업보고서를 쓴다(미래 정보 차단).
"""
import io
import os
import re
import subprocess
import sys
import time
import zipfile
import xml.etree.ElementTree as ET

import pandas as pd
import requests

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "signal-bot"))
import buyback_quality as BQ  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "data"); os.makedirs(D, exist_ok=True)
API = "https://opendart.fss.or.kr/api"
KEY = (os.environ.get("DART_API_KEY") or "").strip()
if not KEY:
    print("DART_API_KEY_MISSING"); sys.exit(2)
calls = 0


def get(path, **params):
    global calls
    for attempt in range(4):
        try:
            calls += 1
            j = requests.get(f"{API}/{path}", params={"crtfc_key": KEY, **params}, timeout=30).json()
            if j.get("status") == "020":
                print("rate limit", calls); time.sleep(60); continue
            return j
        except Exception as e:
            print("retry", path, e); time.sleep(2 + attempt)
    return {}


def num(s):
    s = re.sub(r"[^\d\-]", "", str(s or ""))
    return float(s) if s not in ("", "-") else None


# 공시 목록
subprocess.run(["git", "fetch", "-q", "--depth", "1", "origin", "bt-data-dart"], check=True)
raw = subprocess.run(["git", "show", "FETCH_HEAD:dart_filings.csv.gz"], capture_output=True, check=True).stdout
f = pd.read_csv(io.BytesIO(raw), compression="gzip", dtype={"code": str, "rcept_dt": str, "rcept_no": str})
f["code"] = f.code.str.zfill(6)
f["nm"] = f.report_nm.str.replace(r"\s+", "", regex=True)
f = f[~f.nm.str.startswith("[") & f.code.str.endswith("0")]
bb = f[f.nm.str.contains(BQ.BB_PAT)].drop_duplicates(["code", "rcept_dt"])
vu = f[f.nm.str.contains(BQ.VU_PAT)]
print("자사주 공시", len(bb), "밸류업", len(vu))

z = zipfile.ZipFile(io.BytesIO(requests.get(f"{API}/corpCode.xml", params={"crtfc_key": KEY}, timeout=60).content))
s2c = {(el.findtext("stock_code") or "").strip(): el.findtext("corp_code")
       for el in ET.fromstring(z.read(z.namelist()[0])).iter("list") if (el.findtext("stock_code") or "").strip()}

fy_cache = {}


def fy_info(corp, year):
    """(발행주식총수 보통주, 자본총계)"""
    k = (corp, year)
    if k in fy_cache:
        return fy_cache[k]
    sh = eq = None
    j = get("stockTotqySttus.json", corp_code=corp, bsns_year=str(year), reprt_code="11011")
    for it in j.get("list", []):
        if (it.get("se") or "").strip() in ("보통주", "보통주식"):
            sh = num(it.get("istc_totqy")) or num(it.get("now_to_isu_stock_totqy"))
    j = get("fnlttSinglAcnt.json", corp_code=corp, bsns_year=str(year), reprt_code="11011")
    rows = j.get("list", [])
    for div in ("CFS", "OFS"):
        cand = [r for r in rows if r.get("fs_div") == div and r.get("sj_div") == "BS"]
        own = [r for r in cand if "지배기업" in (r.get("account_nm") or "") and "소유주" in (r.get("account_nm") or "")]
        tot = [r for r in cand if (r.get("account_nm") or "").strip() == "자본총계"]
        pick = own or tot
        if pick:
            eq = num(pick[0].get("thstrm_amount")); break
    fy_cache[k] = (sh, eq)
    return fy_cache[k]


out = []
for n, (_, r) in enumerate(bb.iterrows()):
    corp = s2c.get(r.code)
    txt = BQ.doc_text(r.rcept_no, KEY)
    trust = "신탁" in r.nm
    amt = BQ.bb_amount(txt, trust)
    m = re.search(r"취득예정주식\s*(?:수)?\s*\(주\)\s*보통주식\s*" + BQ.NUM, txt)
    plan = BQ._n(m.group(1)) if m else None
    pm = re.search(r"(?:취득|계약)\s*목적\s*(.{0,80})", txt)
    burn = bool(pm and "소각" in pm.group(1)) or bool(re.search(r"소각\s*(?:목적|예정|을 위한)", txt))
    y, mo = int(r.rcept_dt[:4]), int(r.rcept_dt[4:6])
    fy = y - 2 if mo <= 3 else y - 1
    sh, eq = fy_info(corp, fy) if corp else (None, None)
    out.append({"rcept_no": r.rcept_no, "rcept_dt": r.rcept_dt, "code": r.code, "trust": trust, "amount": amt,
                "shares_plan": plan, "burn": burn, "fy": fy, "shares": sh, "equity": eq})
    time.sleep(0.15)
    if n % 100 == 0:
        print(n, len(bb), "calls", calls, out[-1], flush=True)
pd.DataFrame(out).to_csv(os.path.join(D, "bb_detail.csv.gz"), index=False)

vo = []
for _, r in vu.iterrows():
    p = BQ.pledge_per_year(BQ.doc_text(r.rcept_no, KEY))
    vo.append({"rcept_no": r.rcept_no, "rcept_dt": r.rcept_dt, "code": r.code, "pledge_year": p})
    time.sleep(0.15)
pd.DataFrame(vo).to_csv(os.path.join(D, "bb_valueup.csv.gz"), index=False)
print("완료 calls", calls, "자사주", len(out), "금액 있음", sum(1 for o in out if o["amount"]),
      "자본 있음", sum(1 for o in out if o["equity"]), "밸류업", len(vo), "약속액 있음", sum(1 for o in vo if o["pledge_year"]))
