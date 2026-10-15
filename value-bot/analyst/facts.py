"""analyst/facts.py — analyst_raw/*.json → 종목별 팩트시트(텍스트·JSON)

사용: python facts.py <raw_dir> <out_dir>
"""
import json
import os
import re
import sys

RAW, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)


def n(s):
    s = str(s or "").replace(",", "").strip()
    if s in ("", "-", "None"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def load(t):
    p = os.path.join(RAW, f"{t}.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


ACC = {
    "rev": ["매출액", "수익(매출액)", "영업수익", "매출", "보험수익"],
    "op": ["영업이익", "영업이익(손실)"],
    "ni": ["당기순이익(손실)", "당기순이익", "분기순이익(손실)", "반기순이익(손실)", "분기순이익", "반기순이익"],
    "assets": ["자산총계"], "liab": ["부채총계"], "equity": ["자본총계"],
}


def pick(items, key, fs, field):
    for it in items:
        if it.get("fs_div") == fs and it.get("account_nm", "").strip() in ACC[key]:
            v = n(it.get(field))
            if v is not None:
                return v
    return None


def annual(d):
    """연도 → {rev, op, ni, assets, liab, equity} (억원). 연결 우선."""
    res = {}
    for y, items in sorted((d.get("annual") or {}).items()):
        if not items:
            continue
        fs = "CFS" if any(i.get("fs_div") == "CFS" for i in items) else "OFS"
        for off, field in ((0, "thstrm_amount"), (1, "frmtrm_amount"), (2, "bfefrmtrm_amount")):
            yr = int(y) - off
            if yr in res:
                continue
            row = {k: pick(items, k, fs, field) for k in ACC}
            row = {k: (v / 1e8 if v is not None else None) for k, v in row.items()}
            if row.get("equity") is None and row.get("assets") is not None and row.get("liab") is not None:
                row["equity"] = row["assets"] - row["liab"]
            if any(v is not None for v in row.values()):
                row["fs"] = fs
                res[yr] = row
    return dict(sorted(res.items()))


def quarters(d, ann):
    """'2025Q1' → {rev, op, ni} (억원, 3개월치)."""
    q = {}
    qd = d.get("quarter") or {}
    for y in (2024, 2025, 2026):
        cum = {}
        for i, rc in enumerate(("11013", "11012", "11014"), 1):
            items = qd.get(f"{y}_{rc}")
            if not items:
                continue
            fs = "CFS" if any(it.get("fs_div") == "CFS" for it in items) else "OFS"
            row = {}
            for k in ("rev", "op", "ni"):
                v = pick(items, k, fs, "thstrm_amount")
                row[k] = v / 1e8 if v is not None else None
                c = pick(items, k, fs, "thstrm_add_amount") if i > 1 else v
                cum.setdefault(k, {})[i] = c / 1e8 if c is not None else None
            q[f"{y}Q{i}"] = row
        a = ann.get(y)
        if a and cum:
            row = {}
            for k in ("rev", "op", "ni"):
                c3 = cum.get(k, {}).get(3)
                row[k] = (a[k] - c3) if (a.get(k) is not None and c3 is not None) else None
            if any(v is not None for v in row.values()):
                q[f"{y}Q4"] = row
    return dict(sorted(q.items()))


def dividends(d, pref=False):
    """연도 → DPS(원), 배당성향(%)."""
    want = "우선주" if pref else "보통주"
    dps, payout = {}, {}
    for y, items in sorted((d.get("dividend") or {}).items()):
        if not items:
            continue
        for it in items:
            se = it.get("se", "")
            for off, f in ((0, "thstrm"), (1, "frmtrm"), (2, "lwfr")):
                yr = int(y) - off
                knd = it.get("stock_knd")
                if "주당" in se and "현금배당금" in se and (knd == want or (knd == "-" and not pref)):
                    v = n(it.get(f))
                    if v is not None and yr not in dps:
                        dps[yr] = v
                if "현금배당성향" in se and "연결" in se:
                    v = n(it.get(f))
                    if v is not None and yr not in payout:
                        payout[yr] = v
    return dict(sorted(dps.items())), dict(sorted(payout.items()))


def interim(d, pref=False):
    want = "우선주" if pref else "보통주"
    for it in d.get("dividend_h1") or []:
        se = it.get("se", "")
        if "주당" in se and "현금배당금" in se and it.get("stock_knd") == want:
            return n(it.get("thstrm"))
    return None


def naver_info(d):
    out = {}
    for it in (d.get("naver") or {}).get("totalInfos", []):
        out[it["code"]] = it.get("value")
    c = (d.get("naver") or {}).get("consensusInfo") or {}
    out["target_mean"] = c.get("priceTargetMean")
    out["recomm"] = c.get("recommMean")
    return out


def kr_amt(s):
    s = (s or "").replace(",", "")
    jo = re.search(r"([\d.]+)조", s)
    eok = re.search(r"([\d.]+)억", s)
    return (float(jo.group(1)) * 10000 if jo else 0) + (float(eok.group(1)) if eok else 0) or None


def monthly(d):
    rows = d.get("monthly")
    if not isinstance(rows, list) or len(rows) < 2:
        return []
    return [(r[0], r[4]) for r in rows[1:] if r and r[4]]


def year_end_prices(m):
    ye = {}
    for dt, c in m:
        ye[int(dt[:4])] = c          # 그 해 마지막 월봉 종가
    return ye


def consensus(d):
    fi = (d.get("fin_annual") or {}).get("financeInfo") or {}
    keys = [t["key"] for t in fi.get("trTitleList", []) if t.get("isConsensus") == "Y"]
    out = {}
    for row in fi.get("rowList", []):
        if row["title"] in ("매출액", "영업이익", "당기순이익", "지배주주순이익", "EPS", "PER", "ROE", "부채비율", "PBR", "주당배당금", "배당수익률"):
            for k in keys:
                v = row["columns"].get(k, {}).get("value")
                out.setdefault(k, {})[row["title"]] = v
    return out


def holdings(d):
    out = []
    for it in d.get("invest_h1") or d.get("invest") or []:
        nm = re.sub(r"\(\*.*?\)|\n", "", it.get("inv_prm", "")).strip()
        if nm in ("합계", "-") or not nm:
            continue
        out.append({"name": nm, "pct": n(it.get("trmend_blce_qota_rt")), "qty": n(it.get("trmend_blce_qy")),
                    "book": (n(it.get("trmend_blce_acntbk_amount")) or 0) / 1e8,
                    "ni": (n(it.get("recent_bsns_year_fnnr_sttus_thstrm_ntpf")) or 0) / 1e8})
    out.sort(key=lambda x: -x["book"])
    return out


def shares(d):
    for it in d.get("shares") or []:
        if it.get("se") == "합계":
            return {"issued": n(it.get("istc_totqy")), "treasury": n(it.get("tesstk_co"))}
    return {}


def main_holders(d):
    rows = d.get("holders") or []
    tot = [r for r in rows if r.get("nm") == "계"]
    top = rows[0] if rows else None
    return {"top": top and (top.get("nm"), top.get("trmend_posesn_stock_qota_rt")),
            "total": tot[0].get("trmend_posesn_stock_qota_rt") if tot else None}


KEYDISC = re.compile(r"자기주식|소각|배당결정|공급계약|합병|분할결정|교환|유상|무상|기업가치|공개매수|투자판단|타법인주식")


def build(t):
    d = load(t)
    if not d:
        return None
    pref = t[-1] != "0"
    ann = annual(d)
    m = monthly(d)
    f = {
        "ticker": t, "name": (d.get("naver") or {}).get("stockName"),
        "annual": ann, "quarters": quarters(d, ann),
        "dps": dividends(d, pref)[0], "payout": dividends(d)[1], "interim2026": interim(d, pref),
        "dps_common": dividends(d, False)[0] if pref else None,
        "naver": naver_info(d), "consensus": consensus(d),
        "year_end": year_end_prices(m), "last_price": m[-1] if m else None,
        "holdings": holdings(d)[:10], "shares": shares(d), "holders": main_holders(d),
        "peers_naver": [(p.get("stockName"), p.get("itemCode"), p.get("marketValue"))
                        for p in (d.get("naver") or {}).get("industryCompareInfo") or []][:6],
        "disclosures": [(x["rcept_dt"], x["report_nm"].strip()) for x in (d.get("disclosures") or [])
                        if KEYDISC.search(x["report_nm"])][:25],
    }
    f["mcap"] = kr_amt(f["naver"].get("marketValue"))
    return f


def fmt(v, nd=0):
    if v is None:
        return "-"
    return f"{v:,.{nd}f}"


def text(f, mcaps):
    L = [f"=== {f['name']} ({f['ticker']}) ===",
         f"현재가 {f['last_price']} 시총 {fmt(f['mcap'])}억 PER {f['naver'].get('per')} PBR {f['naver'].get('pbr')} "
         f"배당수익률 {f['naver'].get('dividendYieldRatio')} 추정PER {f['naver'].get('cnsPer')} 목표가평균 {f['naver'].get('target_mean')} 52주 {f['naver'].get('lowPriceOf52Weeks')}~{f['naver'].get('highPriceOf52Weeks')}"]
    L.append("연도  매출  영업이익  OPM  순이익  부채비율  자본  | 연말주가  DPS  배당성향")
    for y, a in f["annual"].items():
        opm = a["op"] / a["rev"] * 100 if a.get("op") is not None and a.get("rev") else None
        dr = a["liab"] / a["equity"] * 100 if a.get("liab") is not None and a.get("equity") else None
        L.append(f"{y} {fmt(a.get('rev'))} {fmt(a.get('op'))} {fmt(opm,1)}% {fmt(a.get('ni'))} {fmt(dr,0)}% {fmt(a.get('equity'))} | "
                 f"{fmt(f['year_end'].get(y))} {fmt(f['dps'].get(y))} {fmt(f['payout'].get(y),1)}% [{a['fs']}]")
    L.append(f"2026 현재가 {fmt(f['last_price'][1]) if f['last_price'] else '-'} / 2026 중간배당 {f['interim2026']}")
    if f.get("dps_common"):
        L.append(f"보통주 DPS: {f['dps_common']}")
    L.append("분기: " + " | ".join(f"{k} 매출{fmt(v.get('rev'))} OP{fmt(v.get('op'))} NI{fmt(v.get('ni'))}" for k, v in f["quarters"].items()))
    if f["consensus"]:
        L.append(f"컨센서스: {f['consensus']}")
    if f["holdings"]:
        tot_mv = 0
        parts = []
        for h in f["holdings"]:
            mv = None
            mc = mcaps.get(h["name"])
            if mc and h["pct"]:
                mv = mc * h["pct"] / 100
                tot_mv += mv
            parts.append(f"{h['name']} {h['pct']}% 장부{fmt(h['book'])}억" + (f" 시가{fmt(mv)}억" if mv else ""))
        L.append("출자: " + " / ".join(parts) + (f"  → 상장자회사 지분 시가합 {fmt(tot_mv)}억" if tot_mv else ""))
    L.append(f"주식: {f['shares']}  최대주주: {f['holders']}")
    L.append(f"네이버 업종비교: {f['peers_naver']}")
    L.append("주요공시: " + "; ".join(f"{a} {b}" for a, b in f["disclosures"]))
    return "\n".join(L)


if __name__ == "__main__":
    facts = {}
    for fn in sorted(os.listdir(RAW)):
        t = fn[:-5]
        f = build(t)
        if f:
            facts[t] = f
    # 회사명 → 시총(억) — 출자 지분 시가 계산용
    mcaps = {}
    for f in facts.values():
        if f["name"] and f["mcap"]:
            mcaps[f["name"]] = f["mcap"]
            mcaps[f"(주){f['name']}"] = f["mcap"]
            mcaps[f"{f['name']}(주)"] = f["mcap"]
            mcaps[f"주식회사 {f['name']}"] = f["mcap"]
    json.dump(facts, open(os.path.join(OUT, "facts.json"), "w", encoding="utf-8"), ensure_ascii=False, default=str)
    with open(os.path.join(OUT, "facts.txt"), "w", encoding="utf-8") as o:
        for t, f in facts.items():
            o.write(text(f, mcaps) + "\n\n")
    print(len(facts), "종목")
