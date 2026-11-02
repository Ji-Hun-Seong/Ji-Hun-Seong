"""
foreign_flow.py — 외국인 수급 필터 (한국투자증권 Open API 공식 데이터)

데이터: KIS '주식현재가 투자자' (TR FHKST01010900)
  - 종목별 최근 약 30영업일의 개인/외국인/기관 순매수 수량·금액
  - 당일 값은 장 마감 후(대략 16시 이후) 채워짐 → 스윙(일봉 신호 → 다음 날 주문)에 맞음

필요한 환경변수 (.env 또는 systemd Environment):
  KIS_APP_KEY, KIS_APP_SECRET   한국투자증권 KIS Developers에서 발급(조회만 함, 주문 안 함)
  KIS_TOKEN_CACHE (선택)         토큰 캐시 파일 경로, 기본 ~/.cache/kis_token.json

단독 실행 테스트:
  python3 foreign_flow.py 005930 000660 001820
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

BASE = "https://openapi.koreainvestment.com:9443"
TOKEN_CACHE = Path(os.environ.get("KIS_TOKEN_CACHE", "~/.cache/kis_token.json")).expanduser()

# ── 필터 기본값 (여기만 바꾸면 됨) ─────────────────────────────
LOOKBACK_DAYS = 5          # 최근 N영업일 합산
MIN_NET_BUY_EOK = 0.0      # N일 외국인 순매수 합계(억원)가 이 값 초과여야 통과
# ────────────────────────────────────────────────────────────

_last_call = 0.0


def _keys():
    k, s = os.environ.get("KIS_APP_KEY"), os.environ.get("KIS_APP_SECRET")
    if not k or not s:
        raise RuntimeError("KIS_APP_KEY / KIS_APP_SECRET 환경변수가 없습니다")
    return k, s


def get_token() -> str:
    """토큰은 24시간 유효, 발급은 1분에 1번 제한 → 파일에 캐시해서 재사용."""
    if TOKEN_CACHE.exists():
        try:
            c = json.loads(TOKEN_CACHE.read_text())
            if datetime.fromisoformat(c["expires"]) > datetime.now() + timedelta(minutes=30):
                return c["token"]
        except Exception:
            pass
    k, s = _keys()
    r = requests.post(f"{BASE}/oauth2/tokenP", timeout=10,
                      json={"grant_type": "client_credentials", "appkey": k, "appsecret": s})
    r.raise_for_status()
    d = r.json()
    expires = datetime.now() + timedelta(seconds=int(d.get("expires_in", 86400)))
    TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_CACHE.write_text(json.dumps({"token": d["access_token"], "expires": expires.isoformat()}))
    os.chmod(TOKEN_CACHE, 0o600)
    return d["access_token"]


def _num(v) -> float:
    try:
        return float(str(v).replace(",", "") or 0)
    except ValueError:
        return 0.0


def fetch_investor(code: str) -> list[dict]:
    """종목코드(6자리) → 최신일부터 [{date, close, frgn_qty, frgn_eok, orgn_eok, prsn_eok}, ...]"""
    global _last_call
    wait = 0.08 - (time.time() - _last_call)   # 초당 호출 제한 여유있게
    if wait > 0:
        time.sleep(wait)
    k, s = _keys()
    r = requests.get(
        f"{BASE}/uapi/domestic-stock/v1/quotations/inquire-investor", timeout=10,
        headers={"authorization": f"Bearer {get_token()}", "appkey": k, "appsecret": s,
                 "tr_id": "FHKST01010900", "custtype": "P"},
        params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code},
    )
    _last_call = time.time()
    r.raise_for_status()
    d = r.json()
    if d.get("rt_cd") != "0":
        raise RuntimeError(f"KIS 오류 {code}: {d.get('msg_cd')} {d.get('msg1')}")
    rows = []
    for o in d.get("output", []):
        # 장중에는 당일 행이 비어 있음(값이 전부 공란) → 건너뜀
        if not o.get("frgn_ntby_qty") and not o.get("frgn_ntby_tr_pbmn"):
            continue
        rows.append({
            "date": o["stck_bsop_date"],
            "close": _num(o.get("stck_clpr")),
            "frgn_qty": _num(o.get("frgn_ntby_qty")),
            # *_tr_pbmn 단위: 백만원 → 억원으로 변환
            "frgn_eok": _num(o.get("frgn_ntby_tr_pbmn")) / 100,
            "orgn_eok": _num(o.get("orgn_ntby_tr_pbmn")) / 100,
            "prsn_eok": _num(o.get("prsn_ntby_tr_pbmn")) / 100,
        })
    return rows


def summarize(rows: list[dict], days: int = LOOKBACK_DAYS) -> dict:
    recent = rows[:days]
    streak = 0
    for r in rows:
        if r["frgn_qty"] > 0:
            streak += 1
        else:
            break
    return {
        "asof": recent[0]["date"] if recent else None,
        "days": len(recent),
        "frgn_sum_eok": round(sum(r["frgn_eok"] for r in recent), 2),
        "orgn_sum_eok": round(sum(r["orgn_eok"] for r in recent), 2),
        "frgn_buy_streak": streak,   # 연속 순매수 일수(오늘부터 거꾸로)
    }


def foreign_check(code: str, days: int = LOOKBACK_DAYS, min_eok: float = MIN_NET_BUY_EOK) -> dict:
    """
    매수 필터. 반환: {"pass": bool, "reason": str, ...summary}
    데이터 조회 실패 시 pass=False (모르면 안 산다).
    """
    try:
        s = summarize(fetch_investor(code), days)
    except Exception as e:
        return {"pass": False, "reason": f"수급 조회 실패: {e}"}
    if s["days"] < days:
        return {**s, "pass": False, "reason": f"수급 데이터 {s['days']}일뿐(필요 {days}일)"}
    ok = s["frgn_sum_eok"] > min_eok
    sign = "+" if s["frgn_sum_eok"] >= 0 else ""
    reason = f"외국인 {days}일 {sign}{s['frgn_sum_eok']}억 · 연속순매수 {s['frgn_buy_streak']}일"
    return {**s, "pass": ok, "reason": reason}


if __name__ == "__main__":
    codes = sys.argv[1:] or ["005930"]
    for c in codes:
        r = foreign_check(c)
        print(f"{c}  {'통과' if r['pass'] else '제외'}  {r['reason']}")
