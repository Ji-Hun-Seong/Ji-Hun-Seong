"""
live_update.py — universe.csv 의 숫자를 최신 공시·시세로 갱신

    export DART_API_KEY=발급받은키      # https://opendart.fss.or.kr (무료)
    python live_update.py               # 변경 내역만 출력(dry-run)
    python live_update.py --write       # universe.csv 덮어쓰기
    python live_update.py --add 005930  # 새 후보 추가(코스피 여부를 DART corp_cls로 확인)

갱신 항목
  OpenDART  : 시장(corp_cls), 주당배당금 3년(alotMatter), 영업현금흐름 3년·CAPEX·순현금(fnlttSinglAcntAll, 연결)
  네이버 증권 : PER·PBR·배당수익률·시가총액
가져오지 못한 값은 기존 값을 그대로 둔다. 이 스크립트는 네트워크가 막힌 환경에서 작성돼
실제 API 응답으로는 시험하지 못했다. 처음 한 번은 dry-run 결과를 눈으로 확인할 것.
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import re
import sys
import time
import zipfile
import xml.etree.ElementTree as ET

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
DART = "https://opendart.fss.or.kr/api"
UA = {"User-Agent": "Mozilla/5.0 value-dna-bot"}
FIELDS = ["name", "ticker", "market", "kind", "sector", "group", "dps23", "dps24", "dps25", "pbr",
          "yield_pct", "per", "ocf23", "ocf24", "ocf25", "capex25", "net_cash", "mcap", "buyback",
          "flags", "note"]


def _key():
    k = os.environ.get("DART_API_KEY")
    if not k:
        sys.exit("DART_API_KEY 환경변수가 필요합니다.")
    return k


def corp_codes(key) -> dict[str, str]:
    """종목코드(6자리) → DART 고유번호(8자리). 결과는 corp_codes.csv 로 캐시."""
    cache = os.path.join(HERE, "corp_codes.csv")
    if os.path.exists(cache) and time.time() - os.path.getmtime(cache) < 30 * 86400:
        return dict(csv.reader(open(cache, encoding="utf-8")))
    z = zipfile.ZipFile(io.BytesIO(requests.get(f"{DART}/corpCode.xml", params={"crtfc_key": key}, timeout=60).content))
    root = ET.fromstring(z.read(z.namelist()[0]))
    m = {}
    for el in root.iter("list"):
        sc = (el.findtext("stock_code") or "").strip()
        if sc:
            m[sc] = el.findtext("corp_code")
    with open(cache, "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(m.items())
    return m


def dart(path, key, **params):
    r = requests.get(f"{DART}/{path}", params={"crtfc_key": key, **params}, timeout=30).json()
    return r if r.get("status") == "000" else None


def _n(s):
    s = (s or "").replace(",", "").strip()
    if s in ("", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def common_ticker(t):
    """우선주(끝자리 5,7,9 등)는 보통주 코드로 재무를 조회한다: 005387 → 005380."""
    return t[:-1] + "0" if t[-1] != "0" else t


def fetch_dart(row, key, codes, last_fy):
    out = {}
    t = row["ticker"]
    cc = codes.get(common_ticker(t))
    if not cc:
        return out
    info = dart("company.json", key, corp_code=cc)
    if info:
        out["market"] = {"Y": "KOSPI", "K": "KOSDAQ"}.get(info.get("corp_cls"), info.get("corp_cls"))

    # 배당: 사업보고서(11011)의 thstrm/frmtrm/lwfr = 당기/전기/전전기
    alot = dart("alotMatter.json", key, corp_code=cc, bsns_year=str(last_fy), reprt_code="11011")
    if alot:
        want = "우선주" if row["kind"] == "pref" else "보통주"
        for it in alot["list"]:
            if "주당" in it.get("se", "") and "현금배당금" in it.get("se", "") and it.get("stock_knd") == want:
                out["dps25"], out["dps24"], out["dps23"] = _n(it.get("thstrm")), _n(it.get("frmtrm")), _n(it.get("lwfr"))
                break

    # 현금흐름·재무상태: 연결(CFS), 없으면 별도(OFS)
    def fin(year):
        for fs in ("CFS", "OFS"):
            r = dart("fnlttSinglAcntAll.json", key, corp_code=cc, bsns_year=str(year), reprt_code="11011", fs_div=fs)
            if r:
                return r["list"]
        return []

    def pick(items, ids, names, field="thstrm_amount"):
        for it in items:
            if it.get("account_id") in ids or any(n == it.get("account_nm", "").replace(" ", "") for n in names):
                v = _n(it.get(field))
                if v is not None:
                    return v / 1e8          # 원 → 억원
        return None

    OCF = (["ifrs-full_CashFlowsFromUsedInOperatingActivities"], ["영업활동현금흐름", "영업활동으로인한현금흐름"])
    cur = fin(last_fy)
    if cur:
        out["ocf25"] = pick(cur, *OCF)
        out["ocf24"] = pick(cur, *OCF, field="frmtrm_amount")
        capex = pick(cur, ["ifrs-full_PurchaseOfPropertyPlantAndEquipment"], ["유형자산의취득", "유형자산의증가"])
        out["capex25"] = abs(capex) if capex is not None else None
        cash = (pick(cur, ["ifrs-full_CashAndCashEquivalents"], ["현금및현금성자산"]) or 0) + \
               (pick(cur, ["dart_ShortTermDepositsNotClassifiedAsCashEquivalents"], ["단기금융상품"]) or 0)
        debt = sum(v or 0 for v in (
            pick(cur, ["ifrs-full_ShorttermBorrowings"], ["단기차입금"]),
            pick(cur, ["ifrs-full_CurrentPortionOfLongtermBorrowings"], ["유동성장기부채", "유동성장기차입금"]),
            pick(cur, ["dart_BondsIssued", "ifrs-full_BondsIssued"], ["사채"]),
            pick(cur, ["dart_LongTermBorrowingsGross", "ifrs-full_LongtermBorrowings"], ["장기차입금"]),
        ))
        if cash:
            out["net_cash"] = round(cash - debt)
    prev = fin(last_fy - 1)
    if prev:
        out["ocf23"] = pick(prev, *OCF, field="frmtrm_amount")
    return {k: v for k, v in out.items() if v is not None}


def _kr_amount(s):
    """'2조 3,291억' → 23291 (억원)"""
    s = (s or "").replace(",", "")
    jo = re.search(r"([\d.]+)조", s)
    eok = re.search(r"([\d.]+)억", s)
    v = (float(jo.group(1)) * 10000 if jo else 0) + (float(eok.group(1)) if eok else 0)
    return v or None


def fetch_naver(ticker):
    out = {}
    try:
        j = requests.get(f"https://m.stock.naver.com/api/stock/{ticker}/integration", headers=UA, timeout=15).json()
    except Exception:
        return out
    for it in j.get("totalInfos", []):
        code, val = it.get("code"), it.get("value", "")
        num = _n(re.sub(r"[^\d.\-]", "", val)) if val else None
        if code == "per":
            out["per"] = num
        elif code == "pbr":
            out["pbr"] = num
        elif code == "dividendYieldRatio":
            out["yield_pct"] = num
        elif code == "marketValue":
            out["mcap"] = _kr_amount(val)
    return {k: v for k, v in out.items() if v is not None}


def fmt(v):
    if isinstance(v, float):
        return f"{v:.2f}".rstrip("0").rstrip(".") if abs(v) < 100 else str(round(v))
    return str(v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", default=os.path.join(HERE, "universe.csv"))
    ap.add_argument("--fy", type=int, default=None, help="최근 사업연도(기본: 4월 이후면 작년)")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--add", nargs="*", default=[], help="추가할 종목코드")
    a = ap.parse_args()
    key = _key()
    from datetime import date
    today = date.today()
    fy = a.fy or (today.year - 1 if today.month >= 4 else today.year - 2)
    codes = corp_codes(key)
    rows = list(csv.DictReader(open(a.universe, encoding="utf-8-sig")))
    have = {r["ticker"] for r in rows}
    for t in a.add:
        if t not in have:
            rows.append({f: "" for f in FIELDS} | {"ticker": t, "name": t, "kind": "operating",
                                                   "sector": "미분류", "group": "", "buyback": "0"})
    for r in rows:
        upd = {**fetch_dart(r, key, codes, fy), **fetch_naver(r["ticker"])}
        changes = {k: (r.get(k), fmt(v)) for k, v in upd.items() if fmt(v) != (r.get(k) or "")}
        if changes:
            print(r["name"], {k: f"{o or '∅'}→{n}" for k, (o, n) in changes.items()})
            for k, (_, n) in changes.items():
                r[k] = n
        if r.get("market") == "KOSDAQ":
            print(f"  ⚠ {r['name']} 은(는) 코스닥 — 기본 설정에선 추천에서 제외됩니다.")
        time.sleep(0.3)
    if a.write:
        with open(a.universe, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows({k: r.get(k, "") for k in FIELDS} for r in rows)
        open(os.path.join(HERE, "DATA_ASOF"), "w").write(today.isoformat())
        print("universe.csv 갱신 완료 — buyback·flags·note·kind·sector는 직접 확인해 주세요.")


if __name__ == "__main__":
    main()
