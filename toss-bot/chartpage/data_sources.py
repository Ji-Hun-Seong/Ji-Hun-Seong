"""
data_sources.py — 차트 페이지용 데이터

  종목 검색   : DART 기업코드 목록(상장사 전체, 하루 1번 받아서 캐시)  ← DART_API_KEY
  일봉 시세   : 야후 파이낸스 차트 API (키 불필요, 한국 .KS/.KQ · 미국 티커 모두)
  자사주 공시 : DART 공시검색 (주요사항보고서 중 자기주식 관련)        ← DART_API_KEY
  외국인 수급 : 한국투자증권 API (foreign_flow.py)                      ← KIS_APP_KEY/SECRET (없으면 생략)
"""

from __future__ import annotations

import io
import json
import os
import re
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree

import pandas as pd
import requests

CACHE = Path(os.environ.get("CHART_CACHE_DIR", "~/.cache/bbchart")).expanduser()
CACHE.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}

# DART 키가 없을 때도 최소한 검색되게
FALLBACK = {
    "삼성전자": ("005930", "00126380"), "SK하이닉스": ("000660", "00164779"),
    "현대차": ("005380", "00164742"), "NAVER": ("035420", "00266961"),
    "카카오": ("035720", "00258801"), "코웨이": ("021240", None), "세방": ("004360", None), "시디즈": ("134790", None),
}


# ── 종목 목록 / 검색 ─────────────────────────────────
def _dart_key() -> str | None:
    return os.environ.get("DART_API_KEY") or os.environ.get("DART_KEY")


def load_corps() -> list[dict]:
    """[{name, code, corp_code}] — 상장사만. 24시간 캐시."""
    f = CACHE / "corps.json"
    if f.exists() and time.time() - f.stat().st_mtime < 86400:
        return json.loads(f.read_text())
    key = _dart_key()
    corps = []
    if key:
        try:
            r = requests.get("https://opendart.fss.or.kr/api/corpCode.xml",
                             params={"crtfc_key": key}, timeout=30)
            r.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                root = ElementTree.fromstring(z.read(z.namelist()[0]))
            for el in root.iter("list"):
                code = (el.findtext("stock_code") or "").strip()
                if code:
                    corps.append({"name": el.findtext("corp_name").strip(), "code": code,
                                  "corp_code": el.findtext("corp_code").strip()})
        except Exception as e:
            print("DART 기업목록 실패:", e)
    if corps:
        f.write_text(json.dumps(corps, ensure_ascii=False))
        return corps
    if f.exists():                      # 실패하면 오래된 캐시라도 사용
        return json.loads(f.read_text())
    return [{"name": n, "code": c, "corp_code": cc} for n, (c, cc) in FALLBACK.items()]


def search(q: str, limit: int = 8) -> list[dict]:
    q = q.strip()
    if not q:
        return []
    corps = load_corps()
    if re.fullmatch(r"\d{6}", q):
        hit = [c for c in corps if c["code"] == q]
        return hit or [{"name": q, "code": q, "corp_code": None}]
    ql = q.lower().replace(" ", "")
    exact = [c for c in corps if c["name"].lower().replace(" ", "") == ql]
    starts = [c for c in corps if c["name"].lower().startswith(ql) and c not in exact]
    contains = [c for c in corps if ql in c["name"].lower() and c not in exact and c not in starts]
    res = (exact + sorted(starts, key=lambda c: len(c["name"])) + contains)[:limit]
    if not res and re.fullmatch(r"[A-Za-z.\-]{1,10}", q):   # 미국 티커
        res = [{"name": q.upper(), "code": q.upper(), "corp_code": None, "us": True}]
    return res


# ── 일봉 (야후) ──────────────────────────────────────
def _yahoo(symbol: str, rng: str) -> pd.DataFrame | None:
    r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
                     params={"range": rng, "interval": "1d", "events": "div,splits"},
                     headers=UA, timeout=15)
    if r.status_code != 200:
        return None
    res = (r.json().get("chart") or {}).get("result")
    if not res or not res[0].get("timestamp"):
        return None
    res = res[0]
    q = res["indicators"]["quote"][0]
    tz = res.get("meta", {}).get("exchangeTimezoneName", "Asia/Seoul")
    idx = pd.to_datetime(res["timestamp"], unit="s", utc=True).tz_convert(tz).tz_localize(None).normalize()
    df = pd.DataFrame({k: q[k] for k in ("open", "high", "low", "close", "volume")}, index=idx)
    df = df.dropna(subset=["close"])
    df = df[~df.index.duplicated(keep="last")]
    meta = res.get("meta", {})
    df.attrs["currency"] = meta.get("currency", "")
    df.attrs["symbol"] = symbol
    return df if len(df) > 30 else None


def get_ohlcv(code: str, us: bool = False, rng: str = "2y") -> pd.DataFrame:
    """한국 6자리 코드면 .KS → .KQ 순으로 시도."""
    symbols = [code] if us else [f"{code}.KS", f"{code}.KQ"]
    for s in symbols:
        df = _yahoo(s, rng)
        if df is not None:
            df["volume"] = df["volume"].fillna(0)
            return df
    raise LookupError(f"{code} 시세를 찾지 못했습니다")


# ── 자사주 공시 (DART) ───────────────────────────────
BUYBACK_PATTERNS = [
    ("신탁해지", r"자기주식취득신탁계약해지"),
    ("신탁계약", r"자기주식취득신탁계약체결"),
    ("처분결정", r"자기주식처분결정"),
    ("소각결정", r"주식소각결정"),
    ("취득결정", r"자기주식취득결정"),
]


def get_buybacks(corp_code: str | None, days: int = 730) -> list[dict]:
    key = _dart_key()
    if not key or not corp_code:
        return []
    out, page = [], 1
    bgn = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
    while page <= 5:
        r = requests.get("https://opendart.fss.or.kr/api/list.json", timeout=15, params={
            "crtfc_key": key, "corp_code": corp_code, "bgn_de": bgn,
            "pblntf_ty": "B", "page_no": page, "page_count": 100})
        d = r.json()
        if d.get("status") != "000":
            break
        for it in d.get("list", []):
            name = re.sub(r"\s", "", it["report_nm"])
            for typ, pat in BUYBACK_PATTERNS:
                if re.search(pat, name):
                    out.append({"date": f"{it['rcept_dt'][:4]}-{it['rcept_dt'][4:6]}-{it['rcept_dt'][6:]}",
                                "type": typ, "title": it["report_nm"].strip(),
                                "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={it['rcept_no']}"})
                    break
        if page >= int(d.get("total_page", 1)):
            break
        page += 1
    return sorted(out, key=lambda e: e["date"])


# ── 외국인 수급 (KIS, 선택) ──────────────────────────
def get_flows(code: str) -> pd.DataFrame | None:
    if not (os.environ.get("KIS_APP_KEY") and os.environ.get("KIS_APP_SECRET")):
        return None
    try:
        from foreign_flow import fetch_investor
        from bb_strategy import flows_from_rows
        rows = fetch_investor(code)
        return flows_from_rows(rows) if rows else None
    except Exception as e:
        print("수급 실패:", e)
        return None
