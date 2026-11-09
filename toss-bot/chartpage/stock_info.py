"""
stock_info.py — 대시보드 '종목 상세' 화면용 데이터 (종목을 누르면 한 화면에 다 보이게)

한국 종목
  시세·이평선·볼린저 : 네이버 일봉(siseJson, 2년, 외국인 소진율 포함) → 실패하면 야후
  밸류·컨센서스·리포트: 네이버 증권 모바일 API(integration) — 시총·PER·PBR·배당·목표가·증권사 리포트·업종 비교
  투자자 수급       : 네이버(trend, 최근 약 60영업일) — 외국인·기관·개인 순매수 수량(+금액 환산), 외국인 보유율
  재무제표          : 네이버(finance/annual·quarter) — 매출·영업이익·순이익·이익률·ROE·부채비율·EPS·PER·PBR·배당 (컨센서스 포함)
  공시             : DART 최근 120일 전체 공시(중요 공시 표시)                         ← DART_API_KEY
해외 종목(미국·일본·중국·홍콩·대만·유럽 등 야후 파이낸스 심볼)
  시세: 야후 차트 / 밸류·재무·기관 보유: yfinance(설치돼 있으면)

단독 테스트:  python3 stock_info.py 005930      python3 stock_info.py AAPL
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import requests

UA = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
                    "Version/17.0 Mobile/15E148 Safari/604.1"}
NAVER = "https://m.stock.naver.com/api/stock"


# ── 숫자 정리 ─────────────────────────────────────────
def num(v):
    """'+515,900' '46.16%' '9.82배' '22,292원' '-' → float / None"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return None if (isinstance(v, float) and math.isnan(v)) else float(v)
    s = re.sub(r"[,%배원\s+]", "", str(v))
    if s in ("", "-", "N/A"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def eok_from_text(v):
    """'1,280조 3,350억' → 12803350 (억원)"""
    if not v:
        return None
    s = str(v).replace(",", "")
    jo = re.search(r"([\d.]+)조", s)
    ek = re.search(r"([\d.]+)억", s)
    if not jo and not ek:
        return num(s)
    return (float(jo.group(1)) * 10000 if jo else 0) + (float(ek.group(1)) if ek else 0)


def clean(x):
    """JSON으로 보내기 전 NaN/inf → None"""
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return None if (math.isnan(x) or math.isinf(x)) else round(float(x), 6)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def _get(url, params=None, timeout=15):
    r = requests.get(url, params=params, headers=UA, timeout=timeout)
    r.raise_for_status()
    return r


# ── 한국: 시세 ────────────────────────────────────────
ROW = re.compile(r'\["(\d{8})",\s*([\d.]+),\s*([\d.]+),\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\]')


def kr_ohlcv(code: str, days: int = 760) -> pd.DataFrame:
    end = dt.date.today() + dt.timedelta(days=1)
    start = end - dt.timedelta(days=days)
    try:
        r = _get("https://api.finance.naver.com/siseJson.naver", {
            "symbol": code, "requestType": 1, "timeframe": "day",
            "startTime": f"{start:%Y%m%d}", "endTime": f"{end:%Y%m%d}"}, timeout=20)
        rows = ROW.findall(r.text)
        if len(rows) >= 30:
            df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume", "fr"])
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").replace("", np.nan).astype(float)
            df = df[df["close"] > 0]
            df.loc[df["open"] <= 0, "open"] = df["close"]
            df.attrs["src"] = "네이버"
            return df
    except Exception:
        pass
    import data_sources as ds                         # 야후 대체
    df = ds.get_ohlcv(code, us=False, rng="max" if days > 1900 else "2y")
    df.attrs["src"] = "야후"
    return df


def kr_industry_name(industry_code) -> str | None:
    """네이버 업종 번호 → 업종 이름 (예: 278 → 반도체와반도체장비)"""
    j = _get(f"https://m.stock.naver.com/api/stocks/industry/{industry_code}?page=1&pageSize=1").json()
    name = ((j or {}).get("groupInfo") or {}).get("name")
    if not name:
        raise ValueError("업종 이름 없음")            # 빈 값은 저장하지 않게
    return name


# ── 한국: 네이버 integration (밸류·컨센서스·리포트·업종 비교) ───────────
def kr_profile(code: str) -> dict:
    j = _get(f"{NAVER}/{code}/integration").json()
    ti = {x.get("code"): x for x in j.get("totalInfos") or []}
    val = lambda k: (ti.get(k) or {}).get("value")
    desc = lambda k: (ti.get(k) or {}).get("valueDesc")
    out = {
        "name": j.get("stockName"), "industry_code": j.get("industryCode"),
        "mcap_eok": eok_from_text(val("marketValue")),
        "per": num(val("per")), "per_asof": desc("per"), "eps": num(val("eps")),
        "fper": num(val("cnsPer")), "feps": num(val("cnsEps")),
        "pbr": num(val("pbr")), "bps": num(val("bps")),
        "div_yield": num(val("dividendYieldRatio")), "dps": num(val("dividend")), "div_asof": desc("dividend"),
        "foreign_rate": num(val("foreignRate")),
        "hi52": num(val("highPriceOf52Weeks")), "lo52": num(val("lowPriceOf52Weeks")),
        "trading_value": val("accumulatedTradingValue"),
    }
    c = j.get("consensusInfo") or {}
    out["target"] = num(c.get("priceTargetMean"))
    out["recomm"] = num(c.get("recommMean"))            # 5 = 강력매수 … 1 = 매도
    out["consensus_date"] = c.get("createDate")
    out["researches"] = [{"broker": r.get("bnm"), "title": r.get("tit"), "date": r.get("wdt"),
                          "url": f"https://m.stock.naver.com/research/company/{r.get('id')}"} for r in (j.get("researches") or [])[:6]]
    peers = []
    ic = j.get("industryCompareInfo") or []
    for p in ic if isinstance(ic, list) else []:
        try:
            peers.append({"name": p.get("stockName"), "code": p.get("itemCode"),
                          "price": num(p.get("closePrice")), "chg": num(p.get("fluctuationsRatio")),
                          "mcap": p.get("marketValue")})
        except Exception:
            pass
    out["peers"] = peers[:6]
    return out


# ── 한국: 투자자 수급 ──────────────────────────────────
def kr_flows(code: str, n: int = 60) -> list[dict]:
    """최신 → 과거. 수량은 주, 금액(억원)은 종가 × 수량으로 환산한 근사치"""
    rows = _get(f"{NAVER}/{code}/trend", {"pageSize": n}).json() or []
    out = []
    for r in rows:
        close = num(r.get("closePrice")) or 0
        f, o, p = (num(r.get(k)) or 0 for k in ("foreignerPureBuyQuant", "organPureBuyQuant", "individualPureBuyQuant"))
        d = r.get("bizdate", "")
        out.append({"date": f"{d[:4]}-{d[4:6]}-{d[6:8]}", "close": close, "vol": num(r.get("accumulatedTradingVolume")),
                    "frgn": f, "orgn": o, "prsn": p, "frgn_ratio": num(r.get("foreignerHoldRatio")),
                    "frgn_eok": f * close / 1e8, "orgn_eok": o * close / 1e8, "prsn_eok": p * close / 1e8})
    return out


def flow_summary(fl: list[dict]) -> dict:
    if not fl:
        return {}
    s = {}
    for who in ("frgn", "orgn", "prsn"):
        for n in (5, 20, 60):
            s[f"{who}_{n}"] = sum(x[f"{who}_eok"] for x in fl[:n]) if len(fl) >= min(n, 5) else None
        streak = 0
        sign = 1 if fl[0][who] > 0 else -1 if fl[0][who] < 0 else 0
        for x in fl:
            if sign and (x[who] > 0) == (sign > 0) and x[who] != 0:
                streak += 1
            else:
                break
        s[f"{who}_streak"] = streak * sign                 # +3 = 3일 연속 순매수, -2 = 2일 연속 순매도
    r = [x["frgn_ratio"] for x in fl if x["frgn_ratio"] is not None]
    if len(r) >= 2:
        s["frgn_ratio"] = r[0]
        s["frgn_ratio_chg20"] = r[0] - r[min(19, len(r) - 1)]
    vol20 = [x["vol"] for x in fl[:20] if x["vol"]]
    s["avg_tv20_eok"] = sum(x["vol"] * x["close"] for x in fl[:20] if x["vol"]) / 1e8 / max(1, len(vol20))
    return s


# ── 한국: 재무 (네이버 요약 재무) ───────────────────────────
FIN_ROWS = ["매출액", "영업이익", "당기순이익", "영업이익률", "순이익률", "ROE", "부채비율", "당좌비율", "유보율",
            "EPS", "PER", "BPS", "PBR", "주당배당금"]


def kr_finance(code: str, kind: str) -> dict:
    j = _get(f"{NAVER}/{code}/finance/{kind}").json()
    fi = j.get("financeInfo") or {}
    periods = [{"key": t["key"], "title": t["title"].rstrip("."), "est": t.get("isConsensus") == "Y"}
               for t in fi.get("trTitleList") or []]
    rows = {}
    for r in fi.get("rowList") or []:
        if r.get("title"):                        # 네이버가 주는 행 전부 (화면에서 주요 행 먼저)
            rows[r["title"]] = [num((r.get("columns") or {}).get(p["key"], {}).get("value")) for p in periods]
    return {"periods": periods, "rows": rows}


# ── 한국: 공시 ────────────────────────────────────────
KEY_FILINGS = [
    ("자사주", r"자기주식취득|자기주식.*신탁계약체결|주식소각"),
    ("배당", r"현금ㆍ현물배당|현금·현물배당|배당"),
    ("실적", r"영업\(잠정\)실적|잠정실적|매출액또는손익구조"),
    ("수주", r"단일판매|공급계약"),
    ("무상증자", r"무상증자"),
    ("증자·CB", r"유상증자|전환사채|신주인수권부사채|교환사채"),
    ("M&A", r"합병|공개매수|최대주주변경|영업양수|타법인주식"),
    ("지분", r"대량보유|최대주주등소유주식"),
    ("거래소", r"투자경고|투자주의|단기과열|조회공시|매매거래정지|불성실"),
    ("정기보고서", r"사업보고서|반기보고서|분기보고서"),
]
GOOD = {"자사주", "배당", "수주", "무상증자"}
BAD = {"증자·CB", "거래소"}


def kr_filings(corp_code: str | None, days: int = 120) -> list[dict]:
    key = os.environ.get("DART_API_KEY") or os.environ.get("DART_KEY")
    if not key or not corp_code:
        return []
    bgn = (dt.date.today() - dt.timedelta(days=days)).strftime("%Y%m%d")
    out, page = [], 1
    while page <= 3:
        d = _get("https://opendart.fss.or.kr/api/list.json", {
            "crtfc_key": key, "corp_code": corp_code, "bgn_de": bgn, "page_no": page, "page_count": 100}).json()
        if d.get("status") != "000":
            break
        for it in d.get("list", []):
            title = re.sub(r"\s+", " ", it["report_nm"]).strip()
            nospace = title.replace(" ", "")
            tag = next((t for t, p in KEY_FILINGS if re.search(p, nospace)), None)
            if tag is None and re.search(r"임원ㆍ주요주주특정증권|임원·주요주주", nospace):
                tag = "임원매매"
            d8 = it["rcept_dt"]
            out.append({"date": f"{d8[:4]}-{d8[4:6]}-{d8[6:]}", "title": title, "tag": tag,
                        "tone": "good" if tag in GOOD else "bad" if tag in BAD else "neu",
                        "filer": it.get("flr_nm"), "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={it['rcept_no']}"})
        if page >= int(d.get("total_page", 1)):
            break
        page += 1
    return out


# ── 지표 ─────────────────────────────────────────────
def indicators(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    c = d["close"]
    for n in (5, 20, 60, 120):
        d[f"ma{n}"] = c.rolling(n).mean()
    sd = c.rolling(20).std(ddof=0)
    d["bb_up"], d["bb_lo"] = d["ma20"] + 2 * sd, d["ma20"] - 2 * sd
    d["pctb"] = (c - d["bb_lo"]) / (d["bb_up"] - d["bb_lo"])
    d["bw"] = (d["bb_up"] - d["bb_lo"]) / d["ma20"]
    delta = c.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    d["rsi"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    d["vma20"] = d["volume"].rolling(20).mean()
    return d


def tech_summary(d: pd.DataFrame) -> dict:
    last = d.iloc[-1]
    c = d["close"]
    s = {"close": last["close"], "chg": (c.iloc[-1] / c.iloc[-2] - 1) if len(c) > 1 else None,
         "rsi": last["rsi"], "pctb": last["pctb"], "bw": last["bw"]}
    for n in (5, 20, 60, 120):
        s[f"ma{n}"] = last[f"ma{n}"]
        s[f"gap{n}"] = last["close"] / last[f"ma{n}"] - 1 if last[f"ma{n}"] == last[f"ma{n}"] else None
    m5, m20, m60, m120 = (last[f"ma{n}"] for n in (5, 20, 60, 120))
    s["aligned"] = "정배열" if m5 > m20 > m60 > m120 else "역배열" if m5 < m20 < m60 < m120 else "혼조"
    bw = d["bw"].dropna().tail(120)
    s["bw_pctile"] = float((bw < bw.iloc[-1]).mean()) if len(bw) > 20 else None
    s["vol_ratio"] = last["volume"] / last["vma20"] if last["vma20"] else None
    hi, lo = d["high"].tail(250).max(), d["low"].tail(250).min()
    s["hi52"], s["lo52"] = hi, lo
    s["pos52"] = (last["close"] - lo) / (hi - lo) if hi > lo else None
    s["from_hi"] = last["close"] / hi - 1
    for n in (5, 20, 60, 250):
        s[f"ret{n}"] = c.iloc[-1] / c.iloc[-n - 1] - 1 if len(c) > n else None
    # 최근 20일 안의 골든·데드크로스 (5일선 × 20일선, 20일선 × 60일선)
    cross = []
    for a, b in ((5, 20), (20, 60)):
        diff = (d[f"ma{a}"] - d[f"ma{b}"]).tail(21)
        sgn = np.sign(diff)
        for i in range(1, len(sgn)):
            if sgn.iloc[i - 1] < 0 < sgn.iloc[i]:
                cross.append({"type": "golden", "pair": f"{a}/{b}", "date": f"{diff.index[i]:%m-%d}"})
            elif sgn.iloc[i - 1] > 0 > sgn.iloc[i]:
                cross.append({"type": "dead", "pair": f"{a}/{b}", "date": f"{diff.index[i]:%m-%d}"})
    last_by_pair = {}
    for x in cross:                                    # 같은 쌍은 가장 최근 것만
        last_by_pair[x["pair"]] = x
    s["cross"] = list(last_by_pair.values())
    return s


def series(d: pd.DataFrame, n: int = 250) -> dict:
    t = d.tail(n)
    col = lambda k: [None if v != v else round(float(v), 4) for v in t[k]]
    out = {"dates": [f"{x:%Y-%m-%d}" for x in t.index]}
    for k in ("open", "high", "low", "close", "volume", "ma5", "ma20", "ma60", "ma120", "bb_up", "bb_lo", "rsi", "vma20"):
        out[k] = col(k)
    if "fr" in t:
        out["fr"] = col("fr")
    return out


def ohlc(df: pd.DataFrame, us: bool = False) -> dict:
    """대시보드 증권사식 차트용 전체 일봉(상장 이후) — 이평선·볼린저·RSI·주/월/년봉은 브라우저에서 계산"""
    nd = 4 if us else 0
    r = lambda k, n: [None if v != v else (round(float(v), n) if n else int(round(float(v)))) for v in df[k]]
    return {"d": [f"{x:%Y%m%d}" for x in df.index], "o": r("open", nd), "h": r("high", nd), "l": r("low", nd),
            "c": r("close", nd), "v": r("volume", 0)}


# ── 한눈에 보기: 신호 카드 ───────────────────────────────
def _sig(cat, title, value, tone, detail=""):
    return {"cat": cat, "title": title, "value": value, "tone": tone, "detail": detail}


def _eok(v):
    if v is None:
        return "-"
    return f"{v:+,.0f}억" if abs(v) >= 1 else f"{v:+.1f}억"


def signals(tech: dict, prof: dict | None = None, fs: dict | None = None, fin: dict | None = None,
            filings: list | None = None, us: bool = False) -> list[dict]:
    S = []
    t = tech
    # 추세
    tone = "good" if t["aligned"] == "정배열" else "bad" if t["aligned"] == "역배열" else "neu"
    above = [n for n in (20, 60, 120) if t.get(f"gap{n}") is not None and t[f"gap{n}"] > 0]
    S.append(_sig("차트", "이평선 배열", t["aligned"], tone,
                  f"종가가 {', '.join(f'{n}일' for n in above) + '선 위' if above else '20·60·120일선 모두 아래'}"))
    for x in t.get("cross", []):
        S.append(_sig("차트", f"{x['pair']} {'골든' if x['type'] == 'golden' else '데드'}크로스", x["date"],
                      "good" if x["type"] == "golden" else "bad", "최근 20거래일 안"))
    pb = t.get("pctb")
    if pb is not None:
        tone = "bad" if pb > 1 else "good" if pb < 0 else "neu"
        txt = "상단 돌파(과열 주의)" if pb > 1 else "하단 이탈(과매도)" if pb < 0 else "상단 근처" if pb > 0.8 else "하단 근처" if pb < 0.2 else "밴드 중간"
        sq = t.get("bw_pctile")
        S.append(_sig("차트", "볼린저 %b", f"{pb:.2f}", tone, txt + (" · 밴드 수축(스퀴즈)" if sq is not None and sq <= 0.1 else "")))
    r = t.get("rsi")
    if r is not None and r == r:
        S.append(_sig("차트", "RSI(14)", f"{r:.0f}", "bad" if r >= 70 else "good" if r <= 30 else "neu",
                      "과매수" if r >= 70 else "과매도" if r <= 30 else "보통"))
    vr = t.get("vol_ratio")
    if vr is not None and vr == vr:
        S.append(_sig("차트", "거래량", f"{vr:.1f}배", "good" if vr >= 2 else "neu", "20일 평균 대비"))
    if t.get("pos52") is not None:
        p = t["pos52"]
        S.append(_sig("차트", "52주 위치", f"{p * 100:.0f}%", "neu",
                      f"고점 대비 {t['from_hi'] * 100:+.0f}% · 0%=최저 100%=최고"))
    # 수급 (한국)
    if fs:
        for who, label in (("frgn", "외국인"), ("orgn", "기관")):
            v5, v20, st = fs.get(f"{who}_5"), fs.get(f"{who}_20"), fs.get(f"{who}_streak") or 0
            if v5 is None:
                continue
            tone = "good" if (v5 > 0 and (v20 or 0) > 0) else "bad" if (v5 < 0 and (v20 or 0) < 0) else "neu"
            S.append(_sig("수급", f"{label} 순매수", f"5일 {_eok(v5)}", tone,
                          f"20일 {_eok(v20)} · " + (f"{st}일 연속 순매수" if st > 0 else f"{-st}일 연속 순매도" if st < 0 else "보합")))
        if fs.get("frgn_ratio") is not None:
            ch = fs.get("frgn_ratio_chg20") or 0
            S.append(_sig("수급", "외국인 보유율", f"{fs['frgn_ratio']:.2f}%", "good" if ch > 0.3 else "bad" if ch < -0.3 else "neu",
                          f"20일 {ch:+.2f}%p"))
    # 밸류
    if prof:
        per, fper, pbr = prof.get("per"), prof.get("fper"), prof.get("pbr")
        if per is not None or fper is not None:
            p = fper if fper else per
            tone = "good" if p and 0 < p < 10 else "bad" if (p is None or p <= 0 or p > 30) else "neu"
            S.append(_sig("밸류", "PER", f"{per:.1f}배" if per else "적자", tone,
                          f"추정 {fper:.1f}배" if fper else ""))
        if pbr is not None:
            S.append(_sig("밸류", "PBR", f"{pbr:.2f}배", "good" if pbr < 1 else "bad" if pbr > 3 else "neu",
                          "청산가치 아래" if pbr < 1 else ""))
        if prof.get("div_yield") is not None:
            dy = prof["div_yield"]
            S.append(_sig("밸류", "배당수익률", f"{dy:.2f}%", "good" if dy >= 4 else "neu", prof.get("div_asof") or ""))
        if prof.get("target") and t.get("close"):
            up = prof["target"] / t["close"] - 1
            S.append(_sig("밸류", "증권사 목표가", f"{up * 100:+.0f}%", "good" if up > 0.2 else "bad" if up < 0 else "neu",
                          f"평균 {prof['target']:,.0f}{'$' if us else '원'}"))
    # 실적·재무
    if fin:
        q = fin.get("quarter") or {}
        rows, ps = q.get("rows") or {}, q.get("periods") or []
        op = rows.get("영업이익") or []
        idx = [i for i, p in enumerate(ps) if not p["est"] and i < len(op) and op[i] is not None]
        if len(idx) >= 1:
            i = idx[-1]
            prev_y = next((j for j in idx if ps[j]["key"][:4] == str(int(ps[i]["key"][:4]) - 1) and ps[j]["key"][4:] == ps[i]["key"][4:]), None)
            if prev_y is not None and op[prev_y]:
                g = op[i] / abs(op[prev_y]) - 1 if op[prev_y] else None
                S.append(_sig("실적", f"영업이익 {ps[i]['title']}", f"{g * 100:+.0f}% YoY" if g is not None else "-",
                              "good" if g and g > 0.1 else "bad" if g is not None and g < -0.1 else "neu", f"{op[i]:,.0f}{'' if us else '억'}"))
            elif op[i] is not None:
                S.append(_sig("실적", f"영업이익 {ps[i]['title']}", f"{op[i]:,.0f}{'' if us else '억'}",
                              "good" if op[i] > 0 else "bad"))
        a = fin.get("annual") or {}
        dr = (a.get("rows") or {}).get("부채비율") or []
        drv = [v for v, p in zip(dr, a.get("periods") or []) if v is not None and not p["est"]]
        if drv:
            S.append(_sig("실적", "부채비율", f"{drv[-1]:.0f}%", "good" if drv[-1] < 100 else "bad" if drv[-1] > 200 else "neu"))
        roe = (a.get("rows") or {}).get("ROE") or []
        rv = [v for v, p in zip(roe, a.get("periods") or []) if v is not None and not p["est"]]
        if rv:
            S.append(_sig("실적", "ROE", f"{rv[-1]:.1f}%", "good" if rv[-1] >= 12 else "bad" if rv[-1] < 5 else "neu"))
    # 공시
    for f in (filings or [])[:40]:
        if f["tag"] in ("자사주", "수주", "무상증자", "증자·CB", "거래소", "M&A", "실적"):
            S.append(_sig("공시", f["tag"], f["date"][5:], f["tone"], f["title"][:40]))
            if sum(1 for x in S if x["cat"] == "공시") >= 3:
                break
    return S


# ── 한국 종목 상세 ─────────────────────────────────────
def _holdings(j):
    """ETF 응답 어디에 있든 '종목명 + 비중' 목록을 찾음 → [{name, code, w}]"""
    best = []

    def walk(o):
        nonlocal best
        if isinstance(o, list) and len(o) >= 3 and all(isinstance(x, dict) for x in o[:3]):
            x0 = o[0]
            nk = next((k for k in x0 if re.search(r"name|nm$|종목", k, re.I) and isinstance(x0[k], str)), None)
            wk = next((k for k in x0 if re.search(r"weight|ratio|rate|비중", k, re.I) and num(x0[k]) is not None), None)
            if nk and wk and len(o) > len(best):
                ck = next((k for k in x0 if re.search(r"code|cd$", k, re.I)), None)
                best = [{"name": x.get(nk), "code": x.get(ck) if ck else None, "w": num(x.get(wk))} for x in o if x.get(nk)]
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(j)
    best = [h for h in best if h["w"] is not None]
    tot = sum(h["w"] for h in best)
    if 0 < tot <= 1.01 and all(h["w"] <= 1 for h in best):           # 0.0852 처럼 소수로 오면 % 로
        best = [{**h, "w": round(h["w"] * 100, 2)} for h in best]
    return best if sum(h["w"] for h in best) > 0 else []


def kr_etf(code: str) -> dict:
    """ETF 전용 — 총보수·구성 종목 비중·기초지수 (네이버 증권). 재무제표 대신"""
    import etf as E
    out, keys = {"fee": None, "holdings": [], "info": []}, {}
    for path in ("integration", "etfAnalysis"):
        try:
            j = _get(f"{NAVER}/{code}/{path}").json()
        except Exception as e:
            keys[path] = f"오류 {type(e).__name__}"
            continue
        keys[path] = " | ".join(f"{k}:{type(v).__name__}" + (f"[{','.join(list(v[0])[:12])}]" if isinstance(v, list) and v and isinstance(v[0], dict) else
                                  f"{{{','.join(list(v)[:12])}}}" if isinstance(v, dict) else "") for k, v in j.items()) if isinstance(j, dict) else type(j).__name__
        if out["fee"] is None:
            out["fee"] = E._find_fee(j)
        h = _holdings({k: v for k, v in j.items() if k not in ("industryCompareInfo", "researches", "dealTrendInfos")} if isinstance(j, dict) else j)
        if len(h) > len(out["holdings"]):
            out["holdings"] = h
        if path == "etfAnalysis" and isinstance(j, dict):
            top = j.get("etfTop10MajorConstituentAssets") or []
            if top:
                out["holdings"] = _holdings({"t": top + [{}] * 0}) or out["holdings"]
            for key, lab in (("sectorPortfolioList", "sector"), ("countryPortfolioList", "country"), ("assetPortfolioList", "asset")):
                rows = [[x.get("detailTypeName") or x.get("detailTypeCode"), num(x.get("weight"))] for x in j.get(key) or [] if isinstance(x, dict)]
                rows = [r for r in rows if r[0] and r[1]]
                if rows and sum(r[1] for r in rows) <= 1.01:
                    rows = [[r[0], round(r[1] * 100, 2)] for r in rows]
                out[lab] = sorted(rows, key=lambda r: -r[1])[:8]
        if path == "integration":
            for x in j.get("totalInfos") or []:
                k, v = x.get("key"), x.get("value")
                if k and v not in (None, "", "-") and not re.search(r"PER|PBR|EPS|BPS|배당", str(k)):
                    out["info"].append([k, v])
    out["holdings"].sort(key=lambda h: -h["w"])
    out["holdings"] = out["holdings"][:30]
    try:
        c = E._conn()
        r = c.execute("SELECT idx, net FROM px WHERE code=? ORDER BY d DESC LIMIT 1", (code,)).fetchone()
        c.close()
        if r:
            out["idx"], out["net_eok"] = r[0], round((r[1] or 0) / 1e8)
    except Exception:
        pass
    if out["fee"] is None:
        try:
            c = E._conn(); r = c.execute("SELECT fee FROM fee WHERE code=?", (code,)).fetchone(); c.close()
            out["fee"] = r[0] if r else None
        except Exception:
            pass
    return out


def kr_detail(code: str, name: str | None = None, corp_code: str | None = None) -> dict:
    t0 = time.time()
    errs = {}

    def safe(key, fn, default):
        try:
            return fn()
        except Exception as e:
            errs[key] = f"{type(e).__name__}: {str(e)[:120]}"
            return default

    try:
        import data_sources as _ds
        is_etf = any(e["code"] == code for e in _ds.load_etfs())
    except Exception:
        is_etf = False
    if is_etf:
        corp_code = None
    with ThreadPoolExecutor(6) as ex:
        f_et = ex.submit(safe, "etf", lambda: kr_etf(code), None) if is_etf else None
        f_px = ex.submit(kr_ohlcv, code, 20000)         # 상장 이후 전체 (차트 '전체' 기간·주/월/년봉용)
        f_pr = ex.submit(safe, "profile", lambda: kr_profile(code), {})
        f_fl = ex.submit(safe, "flows", lambda: kr_flows(code), [])
        f_fa = ex.submit(safe, "finance", lambda: {} if is_etf else kr_finance(code, "annual"), {})
        f_fq = ex.submit(safe, "finance_q", lambda: {} if is_etf else kr_finance(code, "quarter"), {})
        f_dt = ex.submit(safe, "filings", lambda: kr_filings(corp_code), [])
        # 사업요약·매출비중은 느려서(번역·DART 원문) 화면이 뜬 뒤 extras() 로 따로 받음
        df = f_px.result()
        prof, fl, fa, fq, filings = f_pr.result(), f_fl.result(), f_fa.result(), f_fq.result(), f_dt.result()
    d = indicators(df)
    tech = tech_summary(d)
    fs = flow_summary(fl)
    fin = {"annual": fa, "quarter": fq, "unit": "억원"}
    return clean({
        "us": False, "code": code, "name": prof.get("name") or name or code, "asof": f"{d.index[-1]:%Y-%m-%d}",
        "src": df.attrs.get("src", ""), "profile": prof, "tech": tech, "series": series(d), "ohlc": ohlc(df),
        "flows": fl[::-1], "flow_sum": fs, "finance": fin, "filings": filings[:30], "desc": None, "segments": None,
        "signals": signals(tech, prof, fs, fin, filings), "etf": f_et.result() if f_et else None,
        "links": {"naver": f"https://m.stock.naver.com/domestic/stock/{code}/total",
                  "dart": f"https://dart.fss.or.kr/dsab007/main.do?option=corp&textCrpNm={name or code}"},
        "errors": errs, "took": round(time.time() - t0, 2)})


# ── 회사 소개 (종목 상세 맨 위 '🏢 무슨 회사?') ──────────────────────
_DESC_DIR = os.path.join(os.path.expanduser(os.environ.get("CHART_CACHE_DIR", "~/.cache/bbchart")), "desc")


def _desc_cache(key: str, ttl: float, fn):
    """회사 소개는 잘 안 바뀌어서 30일 저장 (번역도 한 번만). 비어 있으면 저장 안 함"""
    f = os.path.join(_DESC_DIR, re.sub(r"[^\w.-]", "_", key) + ".json")
    try:
        if time.time() - os.path.getmtime(f) < ttl:
            return json.load(open(f, encoding="utf-8"))
    except Exception:
        pass
    v = fn()
    if v and v.get("text") and v.pop("_cache", True):   # 번역 실패(영어 그대로)는 저장 안 함 → 다음에 다시 번역
        try:
            os.makedirs(_DESC_DIR, exist_ok=True)
            json.dump(v, open(f + ".tmp", "w", encoding="utf-8"), ensure_ascii=False)
            os.replace(f + ".tmp", f)
        except Exception:
            pass
    return v


_TR_ERR = {"last": None}


def _tr_google(p: str) -> str:
    r = requests.get("https://translate.googleapis.com/translate_a/single",
                     params={"client": "gtx", "sl": "auto", "tl": "ko", "dt": "t", "q": p}, headers=UA, timeout=10)
    r.raise_for_status()
    return "".join(seg[0] for seg in (r.json() or [[]])[0] if seg and seg[0])


def _tr_google2(p: str) -> str:
    r = requests.get("https://clients5.google.com/translate_a/t",
                     params={"client": "dict-chrome-ex", "sl": "auto", "tl": "ko", "q": p}, headers=UA, timeout=10)
    r.raise_for_status()
    j = r.json()
    x = j[0] if isinstance(j, list) and j else j
    return x[0] if isinstance(x, list) else str(x)


def _tr_mymemory(p: str) -> str:
    out = []
    for q in re.findall(r".{1,450}(?:\s|$)", p, re.S):         # 한 번에 500바이트까지
        r = requests.get("https://api.mymemory.translated.net/get", params={"q": q.strip(), "langpair": "en|ko"}, timeout=12)
        r.raise_for_status()
        t = ((r.json() or {}).get("responseData") or {}).get("translatedText") or ""
        if not t or "MYMEMORY WARNING" in t:
            raise RuntimeError("mymemory 한도")
        out.append(t)
    return " ".join(out)


def ko_translate(text: str) -> str | None:
    """영어 → 한국어 (1,500자씩). 구글 번역 2곳 → MyMemory 순서로 시도 — 서버 IP가 한 곳에서 막혀도 되게. 다 실패하면 None"""
    if not text:
        return None
    parts, buf = [], ""
    for s_ in re.split(r"(?<=[.!?])\s+", text):
        if len(buf) + len(s_) > 1500 and buf:
            parts.append(buf)
            buf = ""
        buf += (" " if buf else "") + s_
    if buf:
        parts.append(buf)
    errs = []
    for fn in (_tr_google, _tr_google2, _tr_mymemory):
        try:
            t = " ".join(fn(p) for p in parts).strip()
            if t and re.search(r"[가-힣]", t):
                _TR_ERR["last"] = None
                return t
            errs.append(f"{fn.__name__}: 한국어 아님")
        except Exception as e:
            errs.append(f"{fn.__name__}: {type(e).__name__} {str(e)[:60]}")
    _TR_ERR["last"] = " / ".join(errs)
    print("[번역 실패]", _TR_ERR["last"], file=sys.stderr)
    return None


def _segs_kr(corp_code):
    import segments
    return segments.kr_segments(corp_code)


def _segs_us(sym):
    import segments
    return segments.us_segments(sym)


def _quiet(fn, *a):
    """회사 소개는 없어도 그만 — 실패해도 '일부 데이터 실패'에 안 띄움"""
    try:
        return fn(*a) or {}
    except Exception:
        return {}


def kr_desc(code: str) -> dict:
    """한국: 에프앤가이드(네이버 기업정보) '기업개요' 문장들"""
    def get():
        r = _get("https://navercomp.wisereport.co.kr/v2/company/c1010001.aspx", {"cmp_cd": code}, timeout=10)
        lis = re.findall(r'<li[^>]*class="dot_cmp"[^>]*>(.*?)</li>', r.text, re.S)
        lines = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", x)).strip() for x in lis]
        lines = [x for x in lines if x]
        return {"text": " ".join(lines), "lines": lines, "src": "에프앤가이드 기업개요"}
    return _desc_cache(f"kr_{code}", 30 * 86400, get)


def _wiki_desc(name: str) -> dict:
    """야후 설명이 비었을 때: 위키백과 (한국어 문서 우선, 없으면 영어 문서 번역)"""
    q = re.sub(r"[,.]|\b(inc|corp|corporation|co|ltd|limited|plc|holdings?|group|sa|ag|nv|se|class [a-z])\b", " ", name or "", flags=re.I).strip()
    if not q:
        return {}
    r = requests.get("https://en.wikipedia.org/w/api.php", headers=UA, timeout=8,
                     params={"action": "query", "format": "json", "list": "search", "srsearch": q + " company", "srlimit": 1})
    hit = ((r.json().get("query") or {}).get("search") or [{}])[0].get("title")
    if not hit:
        return {}
    r = requests.get("https://en.wikipedia.org/w/api.php", headers=UA, timeout=8,
                     params={"action": "query", "format": "json", "titles": hit, "prop": "langlinks|extracts", "lllang": "ko",
                             "exintro": 1, "explaintext": 1, "redirects": 1})
    pg = next(iter(((r.json().get("query") or {}).get("pages") or {}).values()), {})
    ko_title = ((pg.get("langlinks") or [{}])[0]).get("*")
    if ko_title:
        r = requests.get("https://ko.wikipedia.org/api/rest_v1/page/summary/" + requests.utils.quote(ko_title.replace(" ", "_")), headers=UA, timeout=8)
        if r.ok and r.json().get("extract"):
            return {"text": r.json()["extract"], "src": "위키백과(한국어)"}
    en = (pg.get("extract") or "").strip()
    if not en:
        return {}
    ko = ko_translate(en[:3000])
    return {"text": ko or en, "en": en, "translated": bool(ko), "src": "위키백과" + (" · 자동 번역" if ko else ""), "_cache": bool(ko)}


def us_desc(sym: str, en: str, name: str = "") -> dict:
    """해외: 야후 회사 설명(영어) → 한국어 번역. 야후 설명이 없으면 위키백과. 번역 실패하면 영어 그대로(저장은 안 함)"""
    def get():
        if not en:
            try:
                return _wiki_desc(name)
            except Exception:
                return {}
        ko = None
        try:
            ko = ko_translate(en)
        except Exception:
            pass
        return {"text": ko or en, "en": en, "translated": bool(ko), "_cache": bool(ko),
                "src": "야후 파이낸스" + (" · 자동 번역" if ko else " (번역 실패 — 다음에 다시 시도)"), "tr_err": None if ko else _TR_ERR["last"]}
    return _desc_cache(f"us2_{sym}", 30 * 86400, get) if (en or name) else {}     # us2_: 예전에 영어로 저장된 것 무시


# 야후 업종(11개) — 한국어
SECTOR_KO = {"Technology": "기술", "Information Technology": "정보기술", "Financial Services": "금융", "Financials": "금융",
             "Healthcare": "헬스케어", "Health Care": "헬스케어", "Consumer Cyclical": "경기소비재", "Consumer Discretionary": "경기소비재",
             "Consumer Defensive": "필수소비재", "Consumer Staples": "필수소비재", "Communication Services": "커뮤니케이션 서비스",
             "Industrials": "산업재", "Energy": "에너지", "Basic Materials": "소재", "Materials": "소재", "Real Estate": "부동산",
             "Utilities": "유틸리티"}
INDUSTRY_KO = {"Auto Manufacturers": "자동차 제조", "Auto Parts": "자동차 부품", "Semiconductors": "반도체",
               "Semiconductor Equipment & Materials": "반도체 장비·소재", "Consumer Electronics": "가전·전자기기",
               "Software—Infrastructure": "소프트웨어(인프라)", "Software - Infrastructure": "소프트웨어(인프라)",
               "Software—Application": "소프트웨어(응용)", "Software - Application": "소프트웨어(응용)",
               "Internet Content & Information": "인터넷 콘텐츠·정보", "Internet Retail": "온라인 유통", "Banks—Diversified": "대형 은행",
               "Banks - Diversified": "대형 은행", "Banks—Regional": "지역 은행", "Banks - Regional": "지역 은행", "Drug Manufacturers—General": "대형 제약",
               "Drug Manufacturers - General": "대형 제약", "Biotechnology": "바이오", "Electronic Gaming & Multimedia": "게임·멀티미디어",
               "Entertainment": "엔터테인먼트", "Oil & Gas Integrated": "석유·가스(통합)", "Aerospace & Defense": "항공우주·방산",
               "Credit Services": "신용·결제 서비스", "Insurance—Diversified": "종합 보험", "Insurance - Diversified": "종합 보험",
               "Discount Stores": "할인점", "Restaurants": "외식", "Beverages—Non-Alcoholic": "음료", "Beverages - Non-Alcoholic": "음료",
               "Footwear & Accessories": "신발·잡화", "Luxury Goods": "명품", "Specialty Industrial Machinery": "산업 기계",
               "Electronic Components": "전자 부품", "Communication Equipment": "통신 장비", "Telecom Services": "통신 서비스",
               "Conglomerates": "복합 기업", "Tobacco": "담배", "Household & Personal Products": "생활용품·화장품"}


def _ko_label(text: str | None, table: dict) -> str | None:
    """업종 이름 한국어로 — 표에 없으면 번역(한 번 하면 저장)"""
    if not text or re.search(r"[가-힣]", text):
        return text
    if text in table:
        return table[text]
    def get():
        ko = ko_translate(text)
        return {"text": ko, "_cache": True} if ko else {}
    try:
        return _desc_cache("lbl_" + text, 365 * 86400, get).get("text") or text
    except Exception:
        return text


def _ko_name(sym: str, en: str) -> str:
    """해외 종목 이름 한국어로: 자주 찾는 종목 한글 별칭 → 없으면 번역(저장). 실패하면 영어 그대로"""
    try:
        import data_sources as ds
        for k, v in ds.WORLD_KO.items():
            if v == sym:
                return k
    except Exception:
        pass
    if not en or re.search(r"[가-힣]", en):
        return en
    base = re.sub(r"\s*(,?\s*(inc\.?|corp\.?|corporation|co\.?,? ltd\.?|ltd\.?|plc|n\.?v\.?|s\.?a\.?|ag|se|limited))+\s*$", "", en, flags=re.I).strip() or en
    try:
        def get():
            ko = ko_translate(base.title() if base.isupper() else base)
            return {"text": ko, "_cache": True} if ko else {}
        v = _desc_cache("name_" + sym, 365 * 86400, get)
        return v.get("text") or en
    except Exception:
        return en


# ── 미국 종목 상세 ─────────────────────────────────────
def _yf_rows(df, names):
    """yfinance 재무표 → {행: [오래된 → 최신]}, 기간 목록"""
    if df is None or df.empty:
        return [], {}
    cols = sorted(df.columns)
    rows = {}
    for label, keys in names.items():
        k = next((k for k in keys if k in df.index), None)
        if k:
            rows[label] = [None if pd.isna(df.at[k, c]) else float(df.at[k, c]) for c in cols]
    return [{"key": f"{c:%Y%m}", "title": f"{c:%Y.%m}", "est": False} for c in cols], rows


US_ROWS = {"매출액": ["Total Revenue", "Operating Revenue"], "영업이익": ["Operating Income", "Total Operating Income As Reported"],
           "당기순이익": ["Net Income", "Net Income Common Stockholders"], "EPS": ["Diluted EPS", "Basic EPS"]}


def yf_annual(tk) -> dict:
    """yfinance 연간 손익 + 재무상태 → 매출·영업이익·순이익·EPS + 영업이익률·ROE·부채비율(4년치)"""
    ps, rows = _yf_rows(tk.income_stmt, US_ROWS)
    if not ps:
        return {"periods": [], "rows": {}}
    rev, op, ni = rows.get("매출액"), rows.get("영업이익"), rows.get("당기순이익")
    if rev and op:
        rows["영업이익률"] = [o / r * 100 if o is not None and r else None for o, r in zip(op, rev)]
    try:
        bs = tk.balance_sheet
        cols = sorted(tk.income_stmt.columns)
        eq_k = next((k for k in ("Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest") if k in bs.index), None)
        li_k = next((k for k in ("Total Liabilities Net Minority Interest", "Total Liabilities") if k in bs.index), None)
        def at(k, c):
            if not k:
                return None
            m = [x for x in bs.columns if abs((x - c).days) <= 40]
            v = bs.at[k, m[0]] if m else None
            return None if v is None or pd.isna(v) else float(v)
        eq = [at(eq_k, c) for c in cols]
        if ni and any(eq):
            rows["ROE"] = [n / e * 100 if n is not None and e and e > 0 else None for n, e in zip(ni, eq)]
        if li_k and any(eq):
            rows["부채비율"] = [at(li_k, c) / e * 100 if at(li_k, c) is not None and e and e > 0 else None for c, e in zip(cols, eq)]
    except Exception:
        pass
    for k in ("매출액", "영업이익", "당기순이익"):
        if k in rows:
            rows[k] = [None if v is None else v / 1e6 for v in rows[k]]
    return {"periods": ps, "rows": rows}


def yf_rev_est(tk, A: dict):
    """증권사 매출 추정(올해·내년, 야후 revenue_estimate 평균) → 연간 표 뒤에 E 열로 붙임. 영업이익 추정은 야후에 없어 빈칸"""
    try:
        re_ = tk.revenue_estimate
    except Exception:
        return
    if re_ is None or getattr(re_, "empty", True) or not A.get("periods"):
        return
    last = A["periods"][-1]["key"]                     # 'YYYYMM' (마지막 실적 결산월)
    y, m = int(last[:4]), last[4:6]
    for i, k in enumerate(("0y", "+1y")):
        if k not in re_.index:
            continue
        v = re_.at[k, "avg"] if "avg" in re_.columns else None
        if v is None or pd.isna(v):
            continue
        A["periods"].append({"key": f"{y + i + 1}{m}", "title": f"{y + i + 1}.{m}", "est": True})
        for name, vals in A["rows"].items():
            vals.append(float(v) / 1e6 if name == "매출액" else None)


def us_ohlcv(sym: str) -> pd.DataFrame:
    import data_sources as ds
    try:
        return ds.get_ohlcv(sym, us=True, rng="max")
    except Exception:
        import yfinance as yf                      # 야후 차트 API가 막히면 yfinance
        h = yf.Ticker(sym).history(period="2y", auto_adjust=False)
        if h is None or len(h) < 30:
            raise LookupError(f"{sym} 시세를 찾지 못했습니다")
        h.index = pd.to_datetime(h.index).tz_localize(None).normalize()
        return h.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]


def us_detail(sym: str, ohlcv=None) -> dict:
    t0 = time.time()
    errs = {}
    df = None
    if ohlcv:
        try:
            df = ohlcv(sym)
        except Exception:
            df = None
    if df is None or len(df) < 130:
        df = us_ohlcv(sym)
    d = indicators(df)
    tech = tech_summary(d)
    prof, fin, holders = {}, {"unit": "백만$"}, []
    try:
        import yfinance as yf
        tk = yf.Ticker(sym)
        info = tk.info or {}
        g = info.get
        prof = {"name": g("shortName") or g("longName") or sym, "sector": g("sector"), "industry": g("industry"),
                "mcap_usd": g("marketCap"), "per": g("trailingPE"), "fper": g("forwardPE"), "pbr": g("priceToBook"),
                "div_yield": g("dividendYield"), "target": g("targetMeanPrice"), "recomm_key": g("recommendationKey"),
                "inst_pct": g("heldPercentInstitutions"), "insider_pct": g("heldPercentInsiders"),
                "short_pct": g("shortPercentOfFloat"), "roe": g("returnOnEquity"), "de": g("debtToEquity"),
                "opm": g("operatingMargins"), "npm": g("profitMargins"), "rev_growth": g("revenueGrowth"),
                "summary": g("longBusinessSummary") or "", "currency": g("currency") or g("financialCurrency"),
                "exchange": g("fullExchangeName") or g("exchange"), "country": g("country")}
        try:                                          # ADR 등 통화가 섞인 종목도 PBR이 맞게 (시총 ÷ 자본총계)
            import heroes
            prof["pbr"] = heroes.yf_pbr(tk, info, sym)
        except Exception:
            pass
        px_now = float(df["close"].iloc[-1])
        rate = g("dividendRate") or g("trailingAnnualDividendRate")
        prof["div_yield"] = rate / px_now * 100 if rate and px_now else 0.0   # yfinance 버전마다 dividendYield 단위가 달라 직접 계산
        try:
            fin["annual"] = yf_annual(tk)
            yf_rev_est(tk, fin["annual"])
        except Exception as e:
            errs["annual"] = str(e)[:120]
        for kind, src in (("quarter", "quarterly_income_stmt"),):
            try:
                ps, rows = _yf_rows(getattr(tk, src), US_ROWS)
                for k in ("매출액", "영업이익", "당기순이익"):
                    if k in rows:
                        rows[k] = [None if v is None else v / 1e6 for v in rows[k]]
                if "매출액" in rows and "영업이익" in rows:
                    rows["영업이익률"] = [o / r * 100 if o is not None and r else None for o, r in zip(rows["영업이익"], rows["매출액"])]
                fin[kind] = {"periods": ps, "rows": rows}
            except Exception as e:
                errs[kind] = str(e)[:120]
        try:
            ih = tk.institutional_holders
            if ih is not None and not ih.empty:
                for _, r in ih.head(6).iterrows():
                    holders.append({"name": r.get("Holder"), "pct": float(r.get("pctHeld") or 0) * 100,
                                    "chg": float(r.get("pctChange") or 0) * 100 if "pctChange" in r else None})
        except Exception:
            pass
    except ImportError:
        errs["yfinance"] = "yfinance 미설치 — 서버에서 .venv/bin/pip install yfinance"
    except Exception as e:
        errs["yfinance"] = f"{type(e).__name__}: {str(e)[:120]}"
    import data_sources as ds
    mkt, ccy0 = ds.market_of(sym)
    ccy = df.attrs.get("currency") or prof.get("currency") or ccy0
    prof["currency"] = ccy
    fin["unit"] = f"백만 {ccy}"
    desc = None                                                # 사업요약·매출비중은 extras() 로 따로 (화면 먼저)
    prof["name_en"] = prof.get("name") or sym                  # 화면은 전부 한국어로 (원래 영어 이름은 작게)
    prof["name"] = _ko_name(sym, prof["name_en"])
    prof["sector_en"], prof["industry_en"] = prof.get("sector"), prof.get("industry")
    prof["sector"], prof["industry"] = _ko_label(prof.get("sector"), SECTOR_KO), _ko_label(prof.get("industry"), INDUSTRY_KO)
    segs = None
    S = signals(tech, prof, None, fin, None, us=True)
    if prof.get("inst_pct") is not None:
        S.append(_sig("수급", "기관 보유", f"{prof['inst_pct'] * 100:.0f}%", "neu", "발행주식 대비"))
    if prof.get("short_pct") is not None:
        sp_ = prof["short_pct"] * 100
        S.append(_sig("수급", "공매도 비율", f"{sp_:.1f}%", "bad" if sp_ > 10 else "neu", "유통주식 대비"))
    return clean({"us": True, "code": sym, "name": prof.get("name") or sym, "asof": f"{d.index[-1]:%Y-%m-%d}",
                  "mkt": mkt, "ccy": ccy, "src": "야후", "profile": prof, "tech": tech, "series": series(d), "ohlc": ohlc(df, True), "flows": [], "flow_sum": {},
                  "holders": holders, "finance": fin, "filings": [], "signals": S, "desc": desc, "segments": segs,
                  "links": {"yahoo": f"https://finance.yahoo.com/quote/{sym}"},
                  "errors": errs, "took": round(time.time() - t0, 2)})


def extras(it: dict, prof: dict | None = None) -> dict:
    """종목 상세의 느린 부분 — 사업요약(번역)·매출비중(DART 원문 / SEC XBRL). 둘을 동시에 받음 (화면은 먼저 뜨고 나중에 채움)"""
    from concurrent.futures import ThreadPoolExecutor
    prof = prof or {}
    with ThreadPoolExecutor(2) as ex:
        if it.get("us"):
            f1 = ex.submit(lambda: _quiet(us_desc, it["code"], prof.get("summary") or "", prof.get("name_en") or prof.get("name") or ""))
            f2 = ex.submit(lambda: _quiet(_segs_us, it["code"]))
        else:
            f1 = ex.submit(lambda: _quiet(kr_desc, it["code"]))
            f2 = ex.submit(lambda: _quiet(_segs_kr, it.get("corp_code")))
        return {"desc": f1.result(), "segments": f2.result()}


def detail(it: dict, us_ohlcv_fn=None) -> dict:
    if it.get("us"):
        return us_detail(it["code"], us_ohlcv_fn)
    return kr_detail(it["code"], it.get("name"), it.get("corp_code"))


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    for q in sys.argv[1:] or ["005930"]:
        us = not re.fullmatch(r"\d{6}", q)
        r = detail({"code": q.upper() if us else q, "us": us})
        print(json.dumps({k: r[k] for k in ("name", "asof", "src", "errors", "took")}, ensure_ascii=False))
        for s in r["signals"]:
            print(f"  [{s['cat']}] {s['title']}: {s['value']} ({s['tone']}) {s['detail']}")
