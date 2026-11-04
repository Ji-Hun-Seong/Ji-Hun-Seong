"""
dart_fin.py — DART 전자공시 재무제표 '최대치' (대시보드 종목 상세 → 📊 재무제표 → 장기·전체)

  · 사업보고서(연간) 2015년~최근 + 올해 최신 분기 누적(1Q/반기/3Q)        ← DART_API_KEY
  · 재무상태표 · 손익계산서 · 현금흐름표 전체 계정 (연결 우선, 없으면 별도)
  · 핵심 지표 자동 계산: 매출·영업이익·순이익·이익률·ROE·ROA·부채비율·유동비율·영업/투자/재무 CF·CAPEX·FCF·
    순현금·EPS·BPS·DPS·배당성향 + (일봉이 있으면) 그해 말 종가 기준 PER·PBR·배당수익률
  · 지난 연도는 한 번 받으면 디스크에 영구 캐시(재무는 안 바뀜), 올해 것은 하루 캐시

단독 테스트:  DART_API_KEY=... python3 dart_fin.py 00126380      (corp_code)
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

DART = "https://opendart.fss.or.kr/api"
CACHE = Path(os.environ.get("CHART_CACHE_DIR", "~/.cache/bbchart")).expanduser() / "dartfin"
FIRST_YEAR = 2015                     # DART 재무 API가 주는 가장 오래된 사업연도
REPRT = {"11011": "연간", "11014": "3Q", "11012": "반기", "11013": "1Q"}
SJ_NAME = {"BS": "재무상태표", "IS": "손익계산서", "CF": "현금흐름표"}


def _key():
    return os.environ.get("DART_API_KEY") or os.environ.get("DART_KEY")


def _n(s):
    s = (s or "").replace(",", "").strip()
    if s in ("", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _cached(name: str, ttl: float | None, fn):
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{name}.json"
    if f.exists() and (ttl is None or time.time() - f.stat().st_mtime < ttl):
        try:
            return json.loads(f.read_text())
        except Exception:
            pass
    val = fn()
    if val is not None:
        f.write_text(json.dumps(val, ensure_ascii=False))
    return val


def _api(path, **params):
    r = requests.get(f"{DART}/{path}", params={"crtfc_key": _key(), **params}, timeout=25)
    r.raise_for_status()
    return r.json()


def fetch_fs(corp: str, year: int, reprt: str = "11011") -> dict:
    """{"fs": "CFS"|"OFS"|None, "list": [...]} — 연결 먼저, 없으면 별도"""
    def get():
        for fs in ("CFS", "OFS"):
            j = _api("fnlttSinglAcntAll.json", corp_code=corp, bsns_year=str(year), reprt_code=reprt, fs_div=fs)
            if j.get("status") == "000" and j.get("list"):
                return {"fs": fs, "list": j["list"]}
            if j.get("status") not in ("013", "000"):        # 013 = 데이터 없음, 그 외(한도 초과 등)는 캐시 안 함
                raise RuntimeError(f"DART {j.get('status')}: {j.get('message')}")
        return {"fs": None, "list": []}
    this_year = dt.date.today().year
    final = reprt == "11011" and year <= this_year - 2 or (reprt == "11011" and year == this_year - 1 and dt.date.today().month >= 5)
    return _cached(f"{corp}_{year}_{reprt}", None if final else 86400, get)


def fetch_div(corp: str, year: int) -> list:
    final = year <= dt.date.today().year - 2 or dt.date.today().month >= 5
    def get():
        j = _api("alotMatter.json", corp_code=corp, bsns_year=str(year), reprt_code="11011")
        if j.get("status") not in ("000", "013"):
            raise RuntimeError(f"DART {j.get('status')}: {j.get('message')}")
        return j.get("list") or []
    return _cached(f"{corp}_{year}_div", None if final else 86400, get)


# ── 계정 찾기 ─────────────────────────────────────────
def _nm(s):
    return re.sub(r"[\s\(\)\[\]ㆍ·.,_-]|^[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩIVX\d]+\.?", "", s or "")


KEY = {   # 지표: (계정ID 후보, 계정명 후보, 표)
    "매출액": (["ifrs-full_Revenue", "ifrs_Revenue"], ["매출액", "수익매출액", "영업수익", "매출", "수익"], "IS"),
    "매출총이익": (["ifrs-full_GrossProfit"], ["매출총이익", "매출총이익손실"], "IS"),
    "영업이익": (["dart_OperatingIncomeLoss"], ["영업이익", "영업이익손실", "영업손익"], "IS"),
    "당기순이익": (["ifrs-full_ProfitLoss"], ["당기순이익", "당기순이익손실", "연결당기순이익", "당기순손익"], "IS"),
    "지배순이익": (["ifrs-full_ProfitLossAttributableToOwnersOfParent"], ["지배기업의소유주에게귀속되는당기순이익", "지배기업소유주지분", "지배기업소유주"], "IS"),
    "자산총계": (["ifrs-full_Assets"], ["자산총계"], "BS"),
    "재고자산": (["ifrs-full_Inventories"], ["재고자산"], "BS"),
    "비유동부채": (["ifrs-full_NoncurrentLiabilities"], ["비유동부채"], "BS"),
    "유동자산": (["ifrs-full_CurrentAssets"], ["유동자산"], "BS"),
    "현금성자산": (["ifrs-full_CashAndCashEquivalents"], ["현금및현금성자산"], "BS"),
    "부채총계": (["ifrs-full_Liabilities"], ["부채총계"], "BS"),
    "유동부채": (["ifrs-full_CurrentLiabilities"], ["유동부채"], "BS"),
    "자본총계": (["ifrs-full_Equity"], ["자본총계"], "BS"),
    "지배자본": (["ifrs-full_EquityAttributableToOwnersOfParent"], ["지배기업의소유주에게귀속되는자본", "지배기업소유주지분"], "BS"),
    "영업CF": (["ifrs-full_CashFlowsFromUsedInOperatingActivities"], ["영업활동현금흐름", "영업활동으로인한현금흐름"], "CF"),
    "투자CF": (["ifrs-full_CashFlowsFromUsedInInvestingActivities"], ["투자활동현금흐름", "투자활동으로인한현금흐름"], "CF"),
    "재무CF": (["ifrs-full_CashFlowsFromUsedInFinancingActivities"], ["재무활동현금흐름", "재무활동으로인한현금흐름"], "CF"),
    "유형자산취득": (["ifrs-full_PurchaseOfPropertyPlantAndEquipment"], ["유형자산의취득", "유형자산의증가", "유형자산취득"], "CF"),
    "무형자산취득": (["ifrs-full_PurchaseOfIntangibleAssets"], ["무형자산의취득", "무형자산의증가"], "CF"),
    "배당금지급": (["ifrs-full_DividendsPaidClassifiedAsFinancingActivities"], ["배당금의지급", "배당금지급"], "CF"),
}
DEBT = (["ifrs-full_ShorttermBorrowings", "ifrs-full_CurrentPortionOfLongtermBorrowings", "dart_BondsIssued",
         "ifrs-full_BondsIssued", "dart_LongTermBorrowingsGross", "ifrs-full_LongtermBorrowings", "ifrs-full_CurrentPortionOfBondsIssued"],
        ["단기차입금", "유동성장기부채", "유동성장기차입금", "유동성사채", "사채", "장기차입금"])
SHORT_DEP = (["dart_ShortTermDepositsNotClassifiedAsCashEquivalents"], ["단기금융상품", "단기예금"])


def _sj(it):
    s = it.get("sj_div")
    return "IS" if s in ("IS", "CIS") else s


def _amt(it, reprt):
    if reprt != "11011" and _sj(it) == "IS" and it.get("thstrm_add_amount") not in (None, ""):
        return _n(it.get("thstrm_add_amount"))                 # 분기 손익은 누적으로
    return _n(it.get("thstrm_amount"))


def _pick(items, ids, names, sj, reprt, field=None):
    cand = [it for it in items if _sj(it) == sj]
    for it in cand:                                          # 계정 ID 우선
        if it.get("account_id") in ids:
            v = _n(it.get(field)) if field else _amt(it, reprt)
            if v is not None:
                return v / 1e8
    for nm in names:                                         # 계정명
        for it in cand:
            if _nm(it.get("account_nm")) == nm:
                v = _n(it.get(field)) if field else _amt(it, reprt)
                if v is not None:
                    return v / 1e8
    return None


def _sum(items, ids, names, sj, reprt, field=None):
    tot, hit, seen = 0.0, False, set()
    for it in items:
        if _sj(it) != sj:
            continue
        key = it.get("account_id") if it.get("account_id") in ids else _nm(it.get("account_nm")) if _nm(it.get("account_nm")) in names else None
        if not key or key in seen:
            continue
        v = _n(it.get(field)) if field else _amt(it, reprt)
        if v is not None:
            tot += v; hit = True; seen.add(key)
    return tot / 1e8 if hit else None


def _has_is(items):
    return any(it.get("sj_div") == "IS" for it in items)


def _clean_is(items):
    """IS와 CIS가 둘 다 있으면 IS만(포괄손익 중복 제거), CIS만 있으면 CIS"""
    if _has_is(items):
        return [it for it in items if it.get("sj_div") != "CIS"]
    return items


MAIN = {   # 대표 계정 표준 순서 (계정 ID 앞부분 일치) — 나머지는 '세부 계정'으로 아래에
    "BS": ["ifrs-full_CurrentAssets", "ifrs-full_CashAndCashEquivalents", "ifrs-full_TradeAndOtherCurrentReceivables",
           "ifrs-full_Inventories", "ifrs-full_NoncurrentAssets", "ifrs-full_PropertyPlantAndEquipment",
           "ifrs-full_IntangibleAssetsOtherThanGoodwill", "ifrs-full_Assets", "ifrs-full_CurrentLiabilities",
           "ifrs-full_NoncurrentLiabilities", "ifrs-full_Liabilities", "ifrs-full_IssuedCapital", "ifrs-full_RetainedEarnings",
           "ifrs-full_EquityAttributableToOwnersOfParent", "ifrs-full_NoncontrollingInterests", "ifrs-full_Equity",
           "ifrs-full_EquityAndLiabilities"],
    "IS": ["ifrs-full_Revenue", "ifrs-full_CostOfSales", "ifrs-full_GrossProfit", "dart_TotalSellingGeneralAdministrative",
           "dart_OperatingIncomeLoss", "dart_OtherGains", "dart_OtherLosses", "ifrs-full_FinanceIncome", "ifrs-full_FinanceCosts",
           "ifrs-full_ShareOfProfitLossOfAssociates", "ifrs-full_ProfitLossBeforeTax", "ifrs-full_IncomeTaxExpense",
           "ifrs-full_ProfitLoss", "ifrs-full_ProfitLossAttributableToOwnersOfParent", "ifrs-full_ProfitLossAttributableToNoncontrolling",
           "ifrs-full_OtherComprehensiveIncome", "ifrs-full_ComprehensiveIncome", "ifrs-full_BasicEarningsLossPerShare",
           "ifrs-full_DilutedEarningsLossPerShare"],
    "CF": ["ifrs-full_CashFlowsFromUsedInOperatingActivities", "ifrs-full_CashFlowsFromUsedInInvestingActivities",
           "ifrs-full_PurchaseOfPropertyPlantAndEquipment", "ifrs-full_PurchaseOfIntangibleAssets",
           "ifrs-full_CashFlowsFromUsedInFinancingActivities", "ifrs-full_DividendsPaid",
           "ifrs-full_IncreaseDecreaseInCashAndCashEquivalents", "dart_CashAndCashEquivalentsAtBeginningOfPeriod",
           "dart_CashAndCashEquivalentsAtEndOfPeriod"],
}
NOISE = {"-표준계정코드 미사용-", "-표준계정코드미사용-", "", None}


PREFIX = {"dart_TotalSellingGeneralAdministrative", "ifrs-full_ShareOfProfitLossOfAssociates", "ifrs-full_IncomeTaxExpense",
          "ifrs-full_ProfitLossAttributableToNoncontrolling", "ifrs-full_PurchaseOfPropertyPlantAndEquipment",
          "ifrs-full_PurchaseOfIntangibleAssets", "dart_CashAndCashEquivalentsAtBeginningOfPeriod", "dart_CashAndCashEquivalentsAtEndOfPeriod",
          "ifrs-full_DividendsPaid"}


def _main_rank(sj, aid):
    aid = aid or ""
    for i, p in enumerate(MAIN[sj]):
        if aid == p or (p in PREFIX and aid.startswith(p)):
            return i
    return None


def statements(periods: list[tuple[str, list, str]]) -> dict:
    """periods = [(라벨, items, reprt)] 최신 → 과거.  표마다 계정 행을 합쳐서 [{name, v, main, unit}]"""
    out = {}
    for sj in ("BS", "IS", "CF"):
        rows, order = {}, []
        for pi, (_, items, reprt) in enumerate(periods):
            for it in sorted([x for x in _clean_is(items) if _sj(x) == sj], key=lambda x: int(x.get("ord") or 9999)):
                nm = (it.get("account_nm") or "").strip()
                aid = it.get("account_id")
                key = aid if aid not in NOISE else "nm:" + _nm(nm)
                if key not in rows:
                    per_share = "PerShare" in (aid or "") or "주당" in nm
                    rows[key] = {"name": nm, "v": [None] * len(periods), "rank": _main_rank(sj, aid), "unit": "원" if per_share else None}
                    order.append(key)
                if rows[key]["v"][pi] is None:
                    v = _amt(it, reprt)
                    if v is not None:
                        rows[key]["v"][pi] = round(v) if rows[key]["unit"] == "원" else round(v / 1e8, 1)
        keep = [rows[k] for k in order if any(x is not None for x in rows[k]["v"])]
        main = sorted([r for r in keep if r["rank"] is not None], key=lambda r: r["rank"])
        rest = [r for r in keep if r["rank"] is None]
        out[sj] = [{"name": r["name"], "v": r["v"], "main": r["rank"] is not None, **({"unit": r["unit"]} if r["unit"] else {})}
                   for r in main + rest]
    return out


def build(corp: str, closes: dict | None = None) -> dict:
    """closes = {"2024": 그해 마지막 종가, ...} (PER·PBR·배당수익률 계산용, 없어도 됨)"""
    if not _key():
        return {"error": "DART_API_KEY가 없어 장기 재무를 못 가져옴"}
    today = dt.date.today()
    years = list(range(today.year - 1, FIRST_YEAR - 1, -1))
    with ThreadPoolExecutor(6) as ex:
        fut = {y: ex.submit(fetch_fs, corp, y) for y in years}
        qfut = {r: ex.submit(fetch_fs, corp, today.year, r) for r in ("11014", "11012", "11013")}
        dfut = {y: ex.submit(fetch_div, corp, y) for y in years[::3]}
        annual = {y: f.result() for y, f in fut.items()}
        quarters = {r: f.result() for r, f in qfut.items()}
        divs = {y: f.result() for y, f in dfut.items()}
    periods = []
    q = next(((r, quarters[r]) for r in ("11014", "11012", "11013") if quarters[r]["list"]), None)
    if q:
        periods.append((f"{str(today.year)[2:]}.{ {'11014': '3Q', '11012': '반기', '11013': '1Q'}[q[0]]}누적", q[1]["list"], q[0]))
    fs_used = {}
    for y in years:
        a = annual[y]
        if a["list"]:
            periods.append((str(y), a["list"], "11011"))
            fs_used[str(y)] = a["fs"]
    # 2015년 보고서의 전기·전전기 숫자로 2013·2014 채우기(핵심 지표만)
    extra = []
    if annual.get(FIRST_YEAR, {}).get("list"):
        it15 = annual[FIRST_YEAR]["list"]
        extra = [(str(FIRST_YEAR - 1), it15, "frmtrm_amount"), (str(FIRST_YEAR - 2), it15, "bfefrmtrm_amount")]
    if not periods:
        return {"error": "DART에 재무제표가 없음(금융지주·신규 상장 등)"}

    labels = [p[0] for p in periods] + [e[0] for e in extra]
    key = {k: [] for k in KEY}
    key.update({"차입금": [], "단기금융상품": []})
    for lab, items, reprt in periods + [(e[0], e[1], "11011") for e in extra]:
        field = next((e[2] for e in extra if e[0] == lab), None)
        its = _clean_is(items)
        for k, (ids, names, sj) in KEY.items():
            key[k].append(_pick(its, ids, names, sj, reprt, field))
        key["차입금"].append(_sum(its, *DEBT, "BS", reprt, field))
        key["단기금융상품"].append(_pick(its, *SHORT_DEP, "BS", reprt, field))

    # 배당(사업보고서 배당 사항: 당기·전기·전전기)
    dps, payout, eps, yld_rep = {}, {}, {}, {}
    for y, lst in divs.items():
        for it in lst:
            se = it.get("se", "")
            vals = {str(y): it.get("thstrm"), str(y - 1): it.get("frmtrm"), str(y - 2): it.get("lwfr")}
            for yy, v in vals.items():
                v = _n(v)
                if v is None:
                    continue
                if "주당" in se and "현금배당금" in se and it.get("stock_knd") in ("보통주", None, "-"):
                    dps.setdefault(yy, v)
                elif "현금배당성향" in se:
                    payout.setdefault(yy, v)
                elif "주당순이익" in se:
                    eps.setdefault(yy, v)
                elif "현금배당수익률" in se and it.get("stock_knd") in ("보통주", None, "-"):
                    yld_rep.setdefault(yy, v)

    def ratio(a, b, pct=True):
        return [None if (x is None or y in (None, 0)) else round(x / y * (100 if pct else 1), 2) for x, y in zip(a, b)]
    K = key
    ni_owner = [o if o is not None else n for o, n in zip(K["지배순이익"], K["당기순이익"])]
    eq_owner = [o if o is not None else e for o, e in zip(K["지배자본"], K["자본총계"])]
    capex = [None if a is None and b is None else abs(a or 0) + abs(b or 0) for a, b in zip(K["유형자산취득"], K["무형자산취득"])]
    fcf = [None if o is None or c is None else round(o - c, 1) for o, c in zip(K["영업CF"], capex)]
    netcash = [None if c is None else round((c or 0) + (s or 0) - (d or 0), 1) for c, s, d in zip(K["현금성자산"], K["단기금융상품"], K["차입금"])]
    annual_only = [not lab.endswith("누적") for lab in labels]
    m = {
        "매출액": K["매출액"], "매출총이익": K["매출총이익"], "영업이익": K["영업이익"], "당기순이익": K["당기순이익"], "지배순이익": K["지배순이익"],
        "영업이익률": ratio(K["영업이익"], K["매출액"]), "순이익률": ratio(K["당기순이익"], K["매출액"]),
        "ROE": [r if ok else None for r, ok in zip(ratio(ni_owner, eq_owner), annual_only)],
        "ROA": [r if ok else None for r, ok in zip(ratio(K["당기순이익"], K["자산총계"]), annual_only)],
        "자산총계": K["자산총계"], "부채총계": K["부채총계"], "자본총계": K["자본총계"], "지배자본": K["지배자본"],
        "부채비율": ratio(K["부채총계"], K["자본총계"]), "유동비율": ratio(K["유동자산"], K["유동부채"]),
        "유동자산": K["유동자산"], "유동부채": K["유동부채"], "재고자산": K["재고자산"], "비유동부채": K["비유동부채"],
        "현금성자산": K["현금성자산"], "차입금": K["차입금"], "순현금": netcash,
        "영업CF": K["영업CF"], "투자CF": K["투자CF"], "재무CF": K["재무CF"], "CAPEX": capex, "FCF": fcf, "배당금지급": K["배당금지급"],
        "EPS": [eps.get(l) for l in labels], "DPS": [dps.get(l) for l in labels], "배당성향": [payout.get(l) for l in labels],
    }
    # 주식 수 ≈ 지배순이익 / EPS → BPS, 그해 말 종가로 PER·PBR·배당수익률
    shares = [None if (n is None or e in (None, 0)) else n * 1e8 / e for n, e in zip(ni_owner, m["EPS"])]
    m["BPS"] = [None if (q is None or s in (None, 0)) else round(q * 1e8 / s) for q, s in zip(eq_owner, shares)]
    if closes:
        px = [closes.get(l) for l in labels]
        m["연말 주가"] = px
        m["PER"] = [None if (p is None or e in (None, 0) or e < 0) else round(p / e, 2) for p, e in zip(px, m["EPS"])]
        m["PBR"] = [None if (p is None or b in (None, 0)) else round(p / b, 2) for p, b in zip(px, m["BPS"])]
        m["배당수익률"] = [None if (p in (None, 0) or d is None) else round(d / p * 100, 2) for p, d in zip(px, m["DPS"])]
    else:
        m["배당수익률"] = [yld_rep.get(l) for l in labels]
    m = {k: [None if v is None else (round(v, 1) if isinstance(v, float) else v) for v in vals] for k, vals in m.items()}
    st = statements(periods)
    return {"src": "DART 전자공시", "labels": labels, "n_statement": len(periods), "fs": fs_used,
            "fs_note": "연결" if all(v == "CFS" for v in fs_used.values()) else "별도" if all(v == "OFS" for v in fs_used.values()) else "연결/별도 혼합",
            "key": {k: v for k, v in m.items() if any(x is not None for x in v)}, "statements": st, "unit": "억원(주당 값은 원)"}


if __name__ == "__main__":
    print(json.dumps(build(sys.argv[1]), ensure_ascii=False)[:3000])
