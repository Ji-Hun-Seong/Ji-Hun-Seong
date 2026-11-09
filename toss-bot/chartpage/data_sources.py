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


_MEM: dict = {}


def load_corps() -> list[dict]:
    """[{name, code, corp_code}] — 상장사만. 메모리 + 파일 24시간 캐시."""
    hit = _MEM.get("corps")
    if hit and time.time() - hit[0] < 86400:
        return hit[1]
    corps = _load_corps_uncached()
    _MEM["corps"] = (time.time(), corps)
    return corps


def _load_corps_uncached() -> list[dict]:
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


# ── 해외 종목 (야후 파이낸스 심볼) ───────────────────────
# 거래소 접미사 → (국가 표시, 통화)
EXCH = {"": ("🇺🇸 미국", "USD"), "T": ("🇯🇵 일본", "JPY"), "SS": ("🇨🇳 중국 상하이", "CNY"), "SZ": ("🇨🇳 중국 선전", "CNY"),
        "BJ": ("🇨🇳 중국 베이징", "CNY"), "HK": ("🇭🇰 홍콩", "HKD"), "TW": ("🇹🇼 대만", "TWD"), "TWO": ("🇹🇼 대만 OTC", "TWD"),
        "L": ("🇬🇧 영국", "GBp"), "DE": ("🇩🇪 독일", "EUR"), "F": ("🇩🇪 프랑크푸르트", "EUR"), "PA": ("🇫🇷 프랑스", "EUR"),
        "AS": ("🇳🇱 네덜란드", "EUR"), "MI": ("🇮🇹 이탈리아", "EUR"), "MC": ("🇪🇸 스페인", "EUR"), "SW": ("🇨🇭 스위스", "CHF"),
        "ST": ("🇸🇪 스웨덴", "SEK"), "CO": ("🇩🇰 덴마크", "DKK"), "OL": ("🇳🇴 노르웨이", "NOK"), "HE": ("🇫🇮 핀란드", "EUR"),
        "BR": ("🇧🇪 벨기에", "EUR"), "VI": ("🇦🇹 오스트리아", "EUR"), "LS": ("🇵🇹 포르투갈", "EUR"), "IR": ("🇮🇪 아일랜드", "EUR"),
        "TO": ("🇨🇦 캐나다", "CAD"), "V": ("🇨🇦 캐나다 벤처", "CAD"), "AX": ("🇦🇺 호주", "AUD"), "NZ": ("🇳🇿 뉴질랜드", "NZD"),
        "SI": ("🇸🇬 싱가포르", "SGD"), "NS": ("🇮🇳 인도 NSE", "INR"), "BO": ("🇮🇳 인도 BSE", "INR"), "JK": ("🇮🇩 인도네시아", "IDR"),
        "BK": ("🇹🇭 태국", "THB"), "KL": ("🇲🇾 말레이시아", "MYR"), "VN": ("🇻🇳 베트남", "VND"), "SA": ("🇧🇷 브라질", "BRL"),
        "MX": ("🇲🇽 멕시코", "MXN"), "JO": ("🇿🇦 남아공", "ZAc"), "TA": ("🇮🇱 이스라엘", "ILA"), "SR": ("🇸🇦 사우디", "SAR"),
        "KS": ("🇰🇷 코스피", "KRW"), "KQ": ("🇰🇷 코스닥", "KRW")}

# 한글 이름으로 찾기 (야후 검색은 영어 이름만 됨) — 자주 찾는 해외 종목
WORLD_KO = {
    # 일본
    "토요타": "7203.T", "도요타": "7203.T", "소니": "6758.T", "닌텐도": "7974.T", "키엔스": "6861.T", "도쿄일렉트론": "8035.T",
    "소프트뱅크그룹": "9984.T", "소프트뱅크": "9984.T", "패스트리테일링": "9983.T", "유니클로": "9983.T", "미쓰비시UFJ": "8306.T",
    "미쓰비시상사": "8058.T", "미쓰이물산": "8031.T", "이토추": "8001.T", "스미토모상사": "8053.T", "마루베니": "8002.T",
    "혼다": "7267.T", "닛산": "7201.T", "히타치": "6501.T", "파나소닉": "6752.T", "캐논": "7751.T", "신에쓰화학": "4063.T",
    "어드반테스트": "6857.T", "레이저텍": "6920.T", "디스코": "6146.T", "다이킨": "6367.T", "화낙": "6954.T", "무라타": "6981.T",
    "NTT": "9432.T", "KDDI": "9433.T", "오리엔탈랜드": "4661.T", "세븐앤아이": "3382.T", "다케다": "4502.T", "다이이찌산쿄": "4568.T",
    "미쓰비시중공업": "7011.T", "가와사키중공업": "7012.T", "IHI": "7013.T", "리쿠르트": "6098.T", "도쿄해상": "8766.T",
    "미즈호": "8411.T", "스미토모미쓰이": "8316.T", "JT": "2914.T", "일본담배": "2914.T", "아식스": "7936.T", "반다이남코": "7832.T",
    "캡콤": "9697.T", "코나미": "9766.T", "스퀘어에닉스": "9684.T", "라쿠텐": "4755.T", "니토리": "9843.T", "시세이도": "4911.T",
    # 중국 본토
    "귀주모태": "600519.SS", "구이저우마오타이": "600519.SS", "마오타이": "600519.SS", "CATL": "300750.SZ", "닝더스다이": "300750.SZ",
    "BYD": "1211.HK", "비야디": "1211.HK", "중국평안": "601318.SS", "초상은행": "600036.SS", "공상은행": "601398.SS",
    "오량액": "000858.SZ", "미디어그룹": "000333.SZ", "메이디": "000333.SZ", "항서제약": "600276.SS", "융기실리콘": "601012.SS",
    "중국석유": "601857.SS", "페트로차이나": "601857.SS", "장강전력": "600900.SS", "이리": "600887.SS", "해천미업": "603288.SS",
    "중신증권": "600030.SS", "BOE": "000725.SZ", "징둥팡": "000725.SZ", "북방화창": "002371.SZ", "중지쉬촹": "300308.SZ",
    "자금광업": "601899.SS", "중국신화에너지": "601088.SS", "하이크비전": "002415.SZ", "럭스셰어": "002475.SZ", "선전이노반스": "300124.SZ",
    # 홍콩
    "텐센트": "0700.HK", "알리바바": "9988.HK", "메이퇀": "3690.HK", "샤오미": "1810.HK", "징둥": "9618.HK", "JD닷컴": "9618.HK",
    "바이두": "9888.HK", "넷이즈": "9999.HK", "HSBC": "0005.HK", "AIA": "1299.HK", "홍콩거래소": "0388.HK", "중국이동": "0941.HK",
    "차이나모바일": "0941.HK", "CNOOC": "0883.HK", "중국해양석유": "0883.HK", "리닝": "2331.HK", "안타스포츠": "2020.HK",
    "팝마트": "9992.HK", "콰이서우": "1024.HK", "리오토": "2015.HK", "샤오펑": "9868.HK", "니오": "9866.HK", "SMIC": "0981.HK",
    "중국건설은행": "0939.HK", "중국은행": "3988.HK", "지리자동차": "0175.HK", "하이디라오": "6862.HK", "트립닷컴": "9961.HK",
    # 대만·기타 아시아
    "TSMC": "2330.TW", "대만반도체": "2330.TW", "폭스콘": "2317.TW", "홍하이": "2317.TW", "미디어텍": "2454.TW", "델타전자": "2308.TW",
    "콴타": "2382.TW", "ASE": "3711.TW", "UMC": "2303.TW", "에이수스": "2357.TW", "릴라이언스": "RELIANCE.NS", "인포시스": "INFY.NS",
    "타타모터스": "TATAMOTORS.NS", "DBS": "D05.SI", "그랩": "GRAB",
    # 유럽
    "ASML": "ASML.AS", "LVMH": "MC.PA", "루이비통": "MC.PA", "에르메스": "RMS.PA", "로레알": "OR.PA", "토탈에너지": "TTE.PA",
    "에어버스": "AIR.PA", "사노피": "SAN.PA", "슈나이더": "SU.PA", "SAP": "SAP.DE", "지멘스": "SIE.DE", "알리안츠": "ALV.DE",
    "폭스바겐": "VOW3.DE", "BMW": "BMW.DE", "벤츠": "MBG.DE", "메르세데스": "MBG.DE", "아디다스": "ADS.DE", "바이엘": "BAYN.DE",
    "라인메탈": "RHM.DE", "인피니언": "IFX.DE", "네슬레": "NESN.SW", "로슈": "ROG.SW", "노바티스": "NOVN.SW", "UBS": "UBSG.SW",
    "노보노디스크": "NOVO-B.CO", "셸": "SHEL.L", "BP": "BP.L", "아스트라제네카": "AZN.L", "HSBC런던": "HSBA.L", "유니레버": "ULVR.L",
    "롤스로이스": "RR.L", "BAE시스템스": "BA.L", "리오틴토": "RIO.L", "페라리": "RACE.MI", "인디텍스": "ITX.MC", "자라": "ITX.MC",
    "스포티파이": "SPOT", "에릭슨": "ERIC-B.ST", "볼보": "VOLV-B.ST", "에퀴노르": "EQNR.OL",
    # 미국(한글)
    "애플": "AAPL", "마이크로소프트": "MSFT", "엔비디아": "NVDA", "구글": "GOOGL", "알파벳": "GOOGL", "아마존": "AMZN", "메타": "META",
    "테슬라": "TSLA", "버크셔": "BRK-B", "버크셔해서웨이": "BRK-B", "브로드컴": "AVGO", "일라이릴리": "LLY", "JP모건": "JPM",
    "비자": "V", "마스터카드": "MA", "월마트": "WMT", "코스트코": "COST", "넷플릭스": "NFLX", "코카콜라": "KO", "펩시": "PEP",
    "맥도날드": "MCD", "스타벅스": "SBUX", "나이키": "NKE", "디즈니": "DIS", "AMD": "AMD", "인텔": "INTC", "퀄컴": "QCOM",
    "마이크론": "MU", "팔란티어": "PLTR", "오라클": "ORCL", "세일즈포스": "CRM", "어도비": "ADBE", "보잉": "BA", "캐터필러": "CAT",
    "엑슨모빌": "XOM", "셰브론": "CVX", "존슨앤존슨": "JNJ", "화이자": "PFE", "P&G": "PG", "홈디포": "HD", "치폴레": "CMG",
    "하워드휴즈": "HHH", "유니버설뮤직": "UMG.AS", "브룩필드": "BN", "힐튼": "HLT", "레스토랑브랜즈": "QSR", "우버": "UBER",
}
WORLD_KO = {k: v for k, v in WORLD_KO.items() if v}


def market_of(sym: str) -> tuple[str, str]:
    """야후 심볼 → (국가 표시, 통화)"""
    suf = sym.rsplit(".", 1)[1].upper() if "." in sym and not re.fullmatch(r"[A-Z]+\.[A-Z]", sym) else ""
    return EXCH.get(suf, EXCH[""])


def _g(sym: str, name: str | None = None) -> dict:
    mk, ccy = market_of(sym)
    return {"name": name or sym, "code": sym, "corp_code": None, "us": True, "mkt": mk, "ccy": ccy}


def yahoo_search(q: str, limit: int = 8) -> list[dict]:
    """야후 검색(영문 이름·티커) — 주식만, 메모리 캐시 1시간"""
    k = "ys:" + q.lower()
    hit = _MEM.get(k)
    if hit and time.time() - hit[0] < 3600:
        return hit[1]
    out = []
    try:
        r = requests.get("https://query2.finance.yahoo.com/v1/finance/search", headers=UA, timeout=8,
                         params={"q": q, "quotesCount": limit + 4, "newsCount": 0, "listsCount": 0, "enableFuzzyQuery": "false"})
        for x in (r.json().get("quotes") or []):
            if x.get("quoteType") not in ("EQUITY", "ETF") or not x.get("symbol"):
                continue
            sym = x["symbol"]
            if sym.endswith((".KS", ".KQ")):       # 한국 종목은 DART 목록 쪽으로
                continue
            it = _g(sym, x.get("shortname") or x.get("longname") or sym)
            it["exch"] = x.get("exchDisp")
            out.append(it)
    except Exception as e:
        print("야후 검색 실패:", e)
    out = out[:limit]
    _MEM[k] = (time.time(), out)
    return out


def load_etfs() -> list[dict]:
    """국내 상장 ETF 목록 (DART 목록엔 ETF가 없음) — ETF 탭이 모으는 state/etf.db 의 최신일, 순자산 큰 순. 1시간 캐시"""
    hit = _MEM.get("etfs")
    if hit and time.time() - hit[0] < (3600 if hit[1] else 60):
        return hit[1]
    out = []
    try:
        import sqlite3
        p = Path(__file__).resolve().parent.parent / "state" / "etf.db"
        c = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=5)
        try:
            rows = c.execute("SELECT code, name FROM px WHERE d = (SELECT MAX(d) FROM days WHERE n > 0) ORDER BY net DESC").fetchall()
        finally:
            c.close()
        out = [{"name": n, "code": k, "corp_code": None, "us": False, "mkt": "🇰🇷 ETF", "etf": True, "_k": n.lower().replace(" ", "")}
               for k, n in rows if k and n]
    except Exception as e:
        print("ETF 목록 실패:", e)
    _MEM["etfs"] = (time.time(), out)
    return out


def search(q: str, limit: int = 8) -> list[dict]:
    """한국(DART 목록 + ETF) → 한글 해외 별칭 → 숫자 코드 규칙(일본·홍콩·중국) → 야후 심볼/검색"""
    q = q.strip()
    if not q:
        return []
    corps = load_corps()
    etfs = load_etfs()
    etf_hit = [e for e in etfs if e["code"].upper() == q.upper()]       # 069500, 0080G0(영문 섞인 새 코드)
    if etf_hit:
        return etf_hit
    if re.fullmatch(r"\d{6}", q):
        hit = [c for c in corps if c["code"] == q]
        if hit:
            return hit
        # 한국에 없는 6자리 = 중국 A주 (6·9 → 상하이, 0·2·3 → 선전, 4·8 → 베이징)
        suf = "SS" if q[0] in "69" else "BJ" if q[0] in "48" else "SZ"
        return [_g(f"{q}.{suf}")]
    if re.fullmatch(r"\d{4}", q):                 # 4자리: 0으로 시작하면 홍콩, 아니면 일본
        return [_g(f"{q}.HK")] if q[0] == "0" else [_g(f"{q}.T"), _g(f"{q}.HK"), _g(f"{q}.TW")]
    if re.fullmatch(r"\d{1,5}\.?(HK)?", q, re.I) and q.upper().endswith("HK"):
        return [_g(f"{int(re.sub(r'\D', '', q)):04d}.HK")]
    ql = q.lower().replace(" ", "")
    exact = [c for c in corps if c["name"].lower().replace(" ", "") == ql]
    starts = [c for c in corps if c["name"].lower().startswith(ql) and c not in exact]
    contains = [c for c in corps if ql in c["name"].lower() and c not in exact and c not in starts]
    # ETF: 띄어쓰기 무시 + 단어 모두 포함('tiger 나스닥' → TIGER 미국나스닥100). 순자산 큰 순
    toks = q.lower().split()
    em = [e for e in etfs if all(t in e["_k"] for t in toks)]
    e_exact = [e for e in em if e["_k"] == ql]
    e_starts = [e for e in em if e["_k"].startswith(toks[0]) and e not in e_exact]
    e_contains = [e for e in em if e not in e_exact and e not in e_starts]
    only_inside = bool(e_contains) and not (exact or starts or contains or e_exact or e_starts)
    exact = exact + e_exact
    # '반도체'처럼 회사 이름에도 많이 들어가는 말이면 ETF 자리를 몇 칸 남김
    res = (exact + sorted(starts, key=lambda c: len(c["name"])) + e_starts
           + contains[:limit - min(3, len(e_contains))] + e_contains)[:limit]
    if only_inside and re.fullmatch(r"[A-Za-z\-]{1,5}", q):              # 미국 티커가 국내 ETF 이름 속에 있어도 티커를 먼저
        res = ([_g(q.upper())] + res)[:limit]
    # 한글 해외 별칭 (정확히 같으면 맨 앞, 앞부분 일치는 뒤에)
    ko = [(k, v) for k, v in WORLD_KO.items() if k.lower().replace(" ", "") == ql] + \
         [(k, v) for k, v in WORLD_KO.items() if k.lower().replace(" ", "").startswith(ql) and k.lower().replace(" ", "") != ql]
    seen = set()
    world = []
    for k, v in ko:
        if v not in seen:
            seen.add(v); world.append(_g(v, k))
    res = (world[:3] + res + world[3:])[:limit] if world and not exact else (res + world)[:limit]
    if res:
        return res
    if re.fullmatch(r"[A-Za-z0-9^=\-]{1,12}(\.[A-Za-z]{1,3})?", q):   # 티커·심볼 (AAPL, 7203.T, MC.PA, BRK-B)
        sym = q.upper()
        ticker_like = bool(re.fullmatch(r"[A-Za-z\-]{1,5}", q)) or "." in q or q[0].isdigit()
        found = [] if re.fullmatch(r"[A-Za-z\-]{1,5}", q) else yahoo_search(q, limit)
        exact_sym = [x for x in found if x["code"].upper() == sym]
        rest = [x for x in found if x["code"].upper() != sym]
        if exact_sym or ticker_like:
            return ((exact_sym or [_g(sym)]) + rest)[:limit]
        return found or [_g(sym)]                  # 'toyota' 같은 영문 이름
    return yahoo_search(q, limit)                  # 영문 회사 이름 (toyota, tencent …)


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


def get_buybacks(corp_code: str | None, days: int = 400) -> list[dict]:
    """자사주 관련 공시. 종목별 6시간 캐시 (장중 새 공시는 봇의 공시 감시가 따로 잡음)"""
    key = _dart_key()
    if not key or not corp_code:
        return []
    mk = f"bb:{corp_code}"
    hit = _MEM.get(mk)
    if hit and time.time() - hit[0] < 6 * 3600:
        return hit[1]
    f = CACHE / f"buyback_{corp_code}.json"
    if f.exists() and time.time() - f.stat().st_mtime < 6 * 3600:
        out = json.loads(f.read_text())
    else:
        out = _get_buybacks_uncached(key, corp_code, days)
        f.write_text(json.dumps(out, ensure_ascii=False))
    _MEM[mk] = (time.time(), out)
    return out


def _get_buybacks_uncached(key: str, corp_code: str, days: int) -> list[dict]:
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
