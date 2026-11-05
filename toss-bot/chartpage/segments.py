"""
매출비중 (사업부문·제품별 매출 구성) — 종목 상세 정보 탭 '🧩 매출비중'

  한국 : DART 최신 사업보고서 원문(document.xml) → 'II. 사업의 내용 > 주요 제품(및 서비스)' 표
         → 사업부문별 비율(%) (비율 칸이 없으면 매출액으로 계산)                 ← DART_API_KEY
  미국 : SEC EDGAR 최신 10-K(외국 회사는 20-F) XBRL → 매출 항목 중 제품/서비스(없으면 사업부문) 축으로 나뉜 값
         → 합계 항목(예: 자동차 = 판매+리스) 은 빼고 비율 계산, 이름은 한국어 번역   ← SEC_UA (선택, "이름 이메일")

  회사마다 표·태그 모양이 달라서 '최대한 맞춰 보는' 방식 — 못 읽으면 빈 값(화면에 안 뜸)
  결과는 30일 저장 (사업보고서·10-K는 1년에 한 번)

단독 테스트:  python3 segments.py kr 00126380      (DART corp_code)
             python3 segments.py us TSLA
"""
from __future__ import annotations

import datetime as dt
import io
import itertools
import json
import os
import re
import sys
import time
import zipfile
import xml.etree.ElementTree as ET

import requests

CACHE = os.path.join(os.path.expanduser(os.environ.get("CHART_CACHE_DIR", "~/.cache/bbchart")), "segments")
UA = {"User-Agent": "Mozilla/5.0"}


def _cache(key: str, ttl: float, fn):
    f = os.path.join(CACHE, re.sub(r"[^\w.-]", "_", key) + ".json")
    try:
        if time.time() - os.path.getmtime(f) < ttl:
            return json.load(open(f, encoding="utf-8"))
    except Exception:
        pass
    v = fn()
    if v and v.get("items"):
        try:
            os.makedirs(CACHE, exist_ok=True)
            json.dump(v, open(f + ".tmp", "w", encoding="utf-8"), ensure_ascii=False)
            os.replace(f + ".tmp", f)
        except Exception:
            pass
    return v


def _num(s: str):
    s = (s or "").replace(",", "").replace("△", "-").strip()
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group()) if m else None


def _finish(items: list[dict], src: str, asof: str, url: str) -> dict:
    items = [x for x in items if x["pct"] and x["pct"] > 0.05]
    items.sort(key=lambda x: -x["pct"])
    if len(items) > 8:                                   # 너무 잘게 나뉘면 나머지는 '기타'
        rest = sum(x["pct"] for x in items[7:])
        items = items[:7] + [{"name": "기타", "pct": rest}]
    return {"items": [{"name": x["name"], "pct": round(x["pct"], 2)} for x in items], "src": src, "asof": asof, "url": url}


# ── 한국: DART 사업보고서 ─────────────────────────────
DROP_KR = re.compile(r"^(합\s*계|총\s*계|소\s*계|계|합계\s*\(.*\)|.*내부\s*거래.*|.*연결\s*조정.*|.*조정\s*및\s*제거.*|.*내부매출.*|.*연결\s*제거.*)$")


def _kr_table(rows: list[list[str]]):
    """주요 제품 표 → [(부문, 비율 or None, 금액 or None)]"""
    hi = next((i for i, r in enumerate(rows[:4]) if any(re.search(r"비율|비중|매출액|매출", c) for c in r)), None)
    if hi is None:
        return []
    head = rows[hi]
    W = len(head)
    p_i = next((i for i, c in enumerate(head) if re.search(r"비율|비중|%", c)), None)
    a_i = next((i for i, c in enumerate(head) if "매출액" in c and i != p_i), None)
    if a_i is None:
        a_i = next((i for i, c in enumerate(head) if re.search(r"매출(?!유형)", c) and i != p_i), None)
    out, grp = [], None
    for r in rows[hi + 1:]:
        if not any(r):
            continue
        full = len(r) >= W
        off = len(r) - W                                  # 앞칸이 합쳐져(rowspan) 빠진 줄은 오른쪽 기준으로 맞춤

        def at(i):
            j = i + off if i is not None else None
            return r[j] if j is not None and 0 <= j < len(r) else ""
        if full or grp is None:
            grp = r[0]
        name = re.sub(r"\s+", " ", grp).strip(" -·")
        if not name or DROP_KR.match(name.replace(" ", "")):
            continue
        pv = at(p_i) if p_i is not None else ""
        pct = None
        m = re.search(r"(-?\d+(?:\.\d+)?)\s*%", " ".join(r)) if p_i is None else None
        if p_i is not None:
            pct = _num(pv)
        elif m:
            pct = float(m.group(1))
        amt = _num(at(a_i)) if a_i is not None else None
        if pct is None and amt is None:
            continue
        out.append((name, pct, amt))
    return out


def kr_segments(corp_code: str) -> dict:
    key = os.environ.get("DART_API_KEY") or os.environ.get("DART_KEY")
    if not key or not corp_code:
        return {}

    def get():
        bgn = (dt.date.today() - dt.timedelta(days=500)).strftime("%Y%m%d")
        j = requests.get("https://opendart.fss.or.kr/api/list.json", timeout=20, params={
            "crtfc_key": key, "corp_code": corp_code, "bgn_de": bgn, "pblntf_ty": "A", "page_count": 100}).json()
        reps = [x for x in j.get("list") or [] if "사업보고서" in x.get("report_nm", "") and "첨부" not in x.get("report_nm", "")]
        if not reps:
            return {}
        rep = max(reps, key=lambda x: x["rcept_dt"])
        rno = rep["rcept_no"]
        r = requests.get("https://opendart.fss.or.kr/api/document.xml", params={"crtfc_key": key, "rcept_no": rno}, timeout=60)
        if not r.content.startswith(b"PK"):
            return {}
        import doc_detail as dd
        z = zipfile.ZipFile(io.BytesIO(r.content))
        blocks = []
        for n in sorted(z.namelist(), key=len):
            if n.lower().endswith(".xml"):
                p = dd._DartParser()
                p.feed(dd._decode(z.read(n)))
                p.close()
                blocks += p.blocks
        # '주요 제품' 제목 뒤 표들 중 처음으로 읽히는 표
        for i, b in enumerate(blocks):
            if b["t"] in ("h", "p") and re.search(r"주요\s*(제품|상품|서비스|사업)", b.get("text", "")) and len(b.get("text", "")) < 60:
                for b2 in blocks[i + 1:i + 12]:
                    if b2["t"] == "h":
                        break
                    if b2["t"] != "table":
                        continue
                    rows = _kr_table(b2["rows"])
                    if len(rows) < 2:
                        continue
                    agg = {}
                    for name, pct, amt in rows:
                        a = agg.setdefault(name, [0.0, 0.0, False])
                        if pct is not None:
                            a[0] += pct
                            a[2] = True
                        if amt is not None:
                            a[1] += amt
                    ps = sum(v[0] for v in agg.values())
                    if all(v[2] for v in agg.values()) and 80 <= ps <= 120:
                        items = [{"name": k, "pct": v[0] / ps * 100} for k, v in agg.items()]
                    else:
                        tot = sum(v[1] for v in agg.values() if v[1] > 0)
                        if not tot:
                            continue
                        items = [{"name": k, "pct": v[1] / tot * 100} for k, v in agg.items() if v[1] > 0]
                    if len(items) >= 1:
                        return _finish(items, f"DART {rep['report_nm'].strip()} · 주요 제품 표", rep["rcept_dt"],
                                       f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rno}")
        return {}
    return _cache(f"kr_{corp_code}", 30 * 86400, get)


# ── 미국: SEC 10-K XBRL ──────────────────────────────
REV = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "RevenueFromContractWithCustomerIncludingAssessedTax",
       "SalesRevenueNet", "Revenue", "RevenueFromContractsWithCustomers"]
AXES = ["ProductOrServiceAxis", "ProductsAndServicesAxis", "StatementBusinessSegmentsAxis", "SegmentsAxis"]


def _ua():
    return {"User-Agent": os.environ.get("SEC_UA") or "toss-bot personal dashboard (set SEC_UA in .env)"}


def _ln(t: str) -> str:
    return t.rsplit("}", 1)[-1]


def _member_name(m: str) -> str:
    m = m.split(":")[-1]
    m = re.sub(r"Member$", "", m)
    m = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", m)
    return m.replace(" And ", " and ").strip()


def _best_split(vals: dict, total: float) -> dict | None:
    """항목들 중 합이 전체 매출과 맞는(±1%) 조합 — 가장 잘게 나뉜 것. 합계 항목(자동차 = 판매+리스)이 섞여 있어도 겹치지 않게"""
    ks = list(vals)
    if len(ks) > 15:
        return None
    best = None
    for mask in range(1, 1 << len(ks)):
        sub = [ks[i] for i in range(len(ks)) if mask >> i & 1]
        if abs(sum(vals[k] for k in sub) - total) <= total * 0.01 and (best is None or len(sub) > len(best)):
            best = sub
    return {k: vals[k] for k in best} if best and len(best) >= 2 else None


def _drop_aggregates(vals: dict) -> dict:
    """(전체와 맞는 조합이 없을 때) 다른 항목들의 합과 같은 항목은 겹치므로 뺌"""
    ks = sorted(vals, key=lambda k: -vals[k])
    keep = dict(vals)
    for k in ks:
        others = [o for o in keep if o != k and keep[o] < keep[k]]
        if len(others) > 14:
            continue
        hit = False
        for n in range(2, len(others) + 1):
            for comb in itertools.combinations(others, n):
                if abs(sum(keep[o] for o in comb) - keep[k]) <= keep[k] * 0.005:
                    hit = True
                    break
            if hit:
                break
        if hit:
            keep.pop(k)
    return keep


def us_segments(sym: str) -> dict:
    def get():
        tick = requests.get("https://www.sec.gov/files/company_tickers.json", headers=_ua(), timeout=30).json()
        cik = next((int(v["cik_str"]) for v in tick.values() if v["ticker"].upper() == sym.upper().replace(".", "-")), None)
        if not cik:
            return {}
        sub = requests.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", headers=_ua(), timeout=20).json()
        R = sub["filings"]["recent"]
        i = next((k for k, f in enumerate(R["form"]) if f in ("10-K", "20-F", "40-F")), None)
        if i is None:
            return {}
        acc, doc, form, fdate = R["accessionNumber"][i].replace("-", ""), R["primaryDocument"][i], R["form"][i], R["filingDate"][i]
        base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}"
        inst = re.sub(r"\.html?$", "", doc) + "_htm.xml"          # iXBRL 10-K 에서 뽑아 둔 XBRL 인스턴스
        x = requests.get(f"{base}/{inst}", headers=_ua(), timeout=60)
        if x.status_code != 200:                         # 옛 방식(별도 인스턴스 파일) — 폴더 목록에서 찾기
            idx = requests.get(f"{base}/index.json", headers=_ua(), timeout=20).json()
            cand = [it["name"] for it in idx.get("directory", {}).get("item", [])
                    if it["name"].endswith(".xml") and not re.search(r"(_cal|_def|_lab|_pre|FilingSummary)", it["name"])]
            if not cand:
                return {}
            x = requests.get(f"{base}/{cand[0]}", headers=_ua(), timeout=60)
        root = ET.fromstring(x.content)
        ctx = {}
        for c in root.iter():
            if _ln(c.tag) != "context":
                continue
            dims = [(e.get("dimension", ""), (e.text or "").strip()) for e in c.iter() if _ln(e.tag) == "explicitMember"]
            sd = ed = None
            for e in c.iter():
                if _ln(e.tag) == "startDate":
                    sd = (e.text or "").strip()
                elif _ln(e.tag) == "endDate":
                    ed = (e.text or "").strip()
            if sd and ed:
                ctx[c.get("id")] = (sd, ed, dims)
        facts = {}                                       # concept → [(ctx, value)]
        for e in root.iter():
            cr = e.get("contextRef")
            if cr and _ln(e.tag) in REV and cr in ctx and (e.text or "").strip():
                try:
                    facts.setdefault(_ln(e.tag), []).append((cr, float(e.text)))
                except ValueError:
                    pass
        for con in REV:
            fs = facts.get(con)
            if not fs:
                continue
            yrs = [(ctx[c][1], v) for c, v in fs if not ctx[c][2]
                   and (dt.date.fromisoformat(ctx[c][1]) - dt.date.fromisoformat(ctx[c][0])).days > 340]
            if not yrs:
                continue
            end, total = max(yrs)
            for ax in AXES:
                vals = {}
                for c, v in fs:
                    sd, ed, dims = ctx[c]
                    if ed == end and len(dims) == 1 and dims[0][0].split(":")[-1] == ax \
                            and (dt.date.fromisoformat(ed) - dt.date.fromisoformat(sd)).days > 340 and v > 0:
                        vals[dims[0][1]] = v
                if len(vals) < 2:
                    continue
                vals = _best_split(vals, total) or _drop_aggregates(vals)
                s = sum(vals.values())
                if s < total * 0.5:                      # 일부만 나뉜 축이면 다른 축 시도
                    continue
                denom = s
                en = {k: _member_name(k) for k in vals}
                ko = {}
                try:
                    from stock_info import ko_translate
                    tr = ko_translate(" | ".join(en.values()))
                    parts = [p.strip() for p in (tr or "").split("|")]
                    if len(parts) == len(en):
                        ko = dict(zip(en, parts))
                except Exception:
                    pass
                items = [{"name": ko.get(k) or en[k], "pct": v / denom * 100} for k, v in vals.items()]
                return {**_finish(items, f"SEC {form} ({fdate}) XBRL · {'제품·서비스별' if 'Product' in ax else '사업부문별'}", end, f"{base}/{doc}"),
                        "en": [en[k] for k in vals]}
        return {}
    return _cache(f"us_{sym.upper()}", 30 * 86400, get)


if __name__ == "__main__":
    kind, arg = sys.argv[1], sys.argv[2]
    print(json.dumps(kr_segments(arg) if kind == "kr" else us_segments(arg), ensure_ascii=False, indent=1))
