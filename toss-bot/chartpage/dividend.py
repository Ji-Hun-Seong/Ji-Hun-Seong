"""
dividend.py — 💰 배당 플래너: 최근 5년 DART 공시로 '언제 받나'를 평균 내고, 새 공시가 뜨면 실제 날짜로 바꿈

  근거 공시 (OpenDART list.json → document.xml 원문 표를 읽음)        ← DART_API_KEY
    · 현금ㆍ현물배당결정   : 배당구분(결산·분기·중간), 1주당 배당금, 배당기준일, 배당금지급 예정일자
    · 주주명부폐쇄기간또는기준일설정 : 결정 공시보다 먼저 나오는 '배당 기준일' (사유에 배당이 있을 때만)
  계산
    · 같은 배당(결산·1분기·반기·3분기…)끼리 묶어 기준일·지급일·기준일→지급 걸린 날·1주당 배당금 평균
    · 올해 공시가 아직 없으면 최근 패턴으로 예상, 공시가 뜨면 그 날짜로 '확정'
    · 언제까지 사야 하나: 결제가 T+2(거래일)라 '매수일+2거래일 ≤ 기준일'인 마지막 거래일. 배당락일 = 그다음 거래일

단독 테스트:  DART_API_KEY=... python3 dividend.py 005930      (시장 전체 다가오는 배당: python3 dividend.py upcoming)
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

import data_sources as ds

YEARS = 5
DOC_FILE = ds.CACHE / "div_docs.json"          # 공시 원문 해석 결과 — 원문은 안 바뀌니 영구 캐시
_doc_lock = threading.Lock()
_docs: dict | None = None

# 한국거래소 휴장일(주말 제외). 2026은 거래소 공지 기준(제헌절·지방선거 포함), 2027은 공휴일 달력으로 잡은 예상치
KRX_HOLIDAYS = {
    "2025-01-01", "2025-01-27", "2025-01-28", "2025-01-29", "2025-01-30", "2025-03-03", "2025-05-01", "2025-05-05",
    "2025-05-06", "2025-06-03", "2025-06-06", "2025-08-15", "2025-10-03", "2025-10-06", "2025-10-07", "2025-10-08",
    "2025-10-09", "2025-12-25", "2025-12-31",
    "2026-01-01", "2026-02-16", "2026-02-17", "2026-02-18", "2026-03-02", "2026-05-01", "2026-05-05", "2026-05-25",
    "2026-06-03", "2026-07-17", "2026-08-17", "2026-09-24", "2026-09-25", "2026-10-05", "2026-10-09", "2026-12-25",
    "2026-12-31",
    "2027-01-01", "2027-02-08", "2027-02-09", "2027-03-01", "2027-05-05", "2027-05-13", "2027-08-16", "2027-09-14",
    "2027-09-15", "2027-09-16", "2027-10-04", "2027-10-11", "2027-12-27", "2027-12-31",
}
HOLIDAY_SURE_UNTIL = dt.date(2026, 12, 31)


def is_trading(d: dt.date) -> bool:
    return d.weekday() < 5 and d.isoformat() not in KRX_HOLIDAYS


def add_trading(d: dt.date, n: int) -> dt.date:
    step = 1 if n >= 0 else -1
    while n:
        d += dt.timedelta(days=step)
        if is_trading(d):
            n -= step
    return d


def buy_deadline(record: dt.date) -> tuple[dt.date, dt.date]:
    """(마지막 매수일, 배당락일). 매수일+2거래일(결제) ≤ 기준일인 마지막 거래일"""
    d = record
    while not is_trading(d):                       # 기준일이 휴일(예: 12/31)이면 그 전 마지막 결제일 기준
        d -= dt.timedelta(days=1)
    last_buy = add_trading(d, -2)
    return last_buy, add_trading(last_buy, 1)


# ── DART ─────────────────────────────────────────────
def _key():
    k = os.environ.get("DART_API_KEY") or os.environ.get("DART_KEY")
    if not k:
        raise RuntimeError("서버 .env 에 DART_API_KEY 가 없음")
    return k


def _list(corp: str, bgn: str, end: str) -> list[dict]:
    out, page = [], 1
    while page <= 30:
        j = requests.get("https://opendart.fss.or.kr/api/list.json", timeout=20,
                         params={"crtfc_key": _key(), "corp_code": corp, "bgn_de": bgn, "end_de": end,
                                 "pblntf_ty": "I", "page_no": page, "page_count": 100}).json()
        if j.get("status") == "013":
            break
        if j.get("status") != "000":
            raise RuntimeError(f"DART {j.get('status')}: {j.get('message')}")
        out += j.get("list") or []
        if page >= int(j.get("total_page") or 1):
            break
        page += 1
    return out


RX_DECIDE = re.compile(r"현금.{0,3}현물\s*배당\s*결정|현금\s*배당\s*결정")
RX_RECORD = re.compile(r"주주명부폐쇄기간\s*또는\s*기준일\s*설정|기준일\s*설정")
RX_DATE = re.compile(r"(20\d\d)\s*[-./년]\s*(\d{1,2})\s*[-./월]\s*(\d{1,2})")


def _date(s):
    m = RX_DATE.search(s or "")
    if not m:
        return None
    try:
        return dt.date(int(m[1]), int(m[2]), int(m[3])).isoformat()
    except ValueError:
        return None


def _rows(blocks):
    """원문 표 → [(라벨, 값들)] (빈 칸·번호 정리)"""
    num = re.compile(r"^[\d가-하]{1,2}[.)]\s*")
    for b in blocks or []:
        if b.get("t") != "table":
            continue
        for r in b["rows"]:
            cells = [c.strip() for c in r if c and c.strip()]
            if cells:
                yield num.sub("", cells[0]).replace(" ", ""), cells[1:]


def parse_decision(blocks) -> dict:
    out, look = {}, 0                                  # look: '1주당 배당금' 줄에 숫자가 없으면 아래 2줄에서 보통주 값을 찾음
    for lab, vals in _rows(blocks):
        v = " ".join(vals)
        nums = [x for x in (_n(y) for y in vals) if x is not None]
        if look:
            look -= 1
            if "보통" in lab and nums and "dps" not in out:
                out["dps"], look = nums[0], 0
                continue
        if "배당구분" in lab and vals:
            out["kind"] = vals[-1].replace(" ", "")
        elif "1주당배당금" in lab:
            if nums and "dps" not in out:
                out["dps"] = nums[0]
            else:
                look = 2
        elif "배당기준일" in lab:
            out["record"] = _date(v)
        elif "지급예정일" in lab or ("지급일" in lab and "배당" in lab):
            out["pay"] = _date(v)
        elif "시가배당" in lab and nums and "yield" not in out:
            out["yield"] = nums[0]
    return out


def parse_record_notice(blocks) -> dict:
    out, why = {}, ""
    for lab, vals in _rows(blocks):
        v = " ".join(vals)
        if "사유" in lab or "목적" in lab:
            why += lab + v
        elif lab.endswith("기준일") and "이사회" not in lab and "record" not in out:
            out["record"] = _date(v)
    if "배당" not in why:
        return {}
    out["kind"] = "분기배당" if "분기" in why else "중간배당" if "중간" in why or "반기" in why else "결산배당" if "결산" in why else ""
    return out


def _n(s):
    s = re.sub(r"[,\s원%]", "", str(s or ""))
    return float(s) if re.fullmatch(r"-?\d+(\.\d+)?", s) else None


def _load_docs():
    global _docs
    if _docs is None:
        try:
            _docs = json.loads(DOC_FILE.read_text())
        except Exception:
            _docs = {}
    return _docs


def _doc(rcept_no: str, kind: str) -> dict:
    with _doc_lock:
        hit = _load_docs().get(rcept_no)
    if hit is not None:
        return hit
    import doc_detail
    d = doc_detail.filing_detail(rcept_no)
    if d.get("error"):
        raise RuntimeError(d["error"])
    res = parse_decision(d.get("blocks")) if kind == "d" else parse_record_notice(d.get("blocks"))
    with _doc_lock:
        _load_docs()[rcept_no] = res
        try:
            DOC_FILE.write_text(json.dumps(_docs, ensure_ascii=False))
        except Exception:
            pass
    return res


# ── 묶기·평균·예상 ─────────────────────────────────────
def slot_of(kind: str, record: str) -> str:
    m = int(record[5:7])
    k = (kind or "").replace(" ", "")
    if "분기" in k or "중간" in k or "반기" in k:
        return f"Q{(m - 1) // 3 + 1}"               # 3·6·9월 기준이면 1·2·3분기
    if "결산" in k or not k:                       # 12월 결산(제도 개편 뒤 2~4월 기준일 포함) / 6월 결산(리츠·인프라펀드 등 반기 결산)
        return "Y" if m in (11, 12, 1, 2, 3, 4) else "H"
    return "X"                                       # 특별배당 등 (평균에서 빼고 기록만)


SLOT_NAME = {"Y": "결산배당", "H": "결산배당(6월 결산)", "Q1": "1분기 배당", "Q2": "반기(2분기) 배당", "Q3": "3분기 배당", "Q4": "4분기 배당", "X": "특별·기타"}


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def build(code: str, today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    corp = next((c for c in ds.load_corps() if c["code"] == code), None)
    if not corp or not corp.get("corp_code"):
        return {"code": code, "error": "DART에서 회사를 찾지 못함(국내 상장 보통주만 됨)"}
    bgn = (today.replace(year=today.year - YEARS) - dt.timedelta(days=60)).strftime("%Y%m%d")
    lst = _list(corp["corp_code"], bgn, today.strftime("%Y%m%d"))
    picks = [(x, "d") for x in lst if RX_DECIDE.search(x.get("report_nm", ""))]
    picks += [(x, "r") for x in lst if RX_RECORD.search(x.get("report_nm", "")) and not RX_DECIDE.search(x.get("report_nm", ""))]
    with ThreadPoolExecutor(6) as ex:
        parsed = list(ex.map(lambda p: (p[0], p[1], _safe_doc(p[0]["rcept_no"], p[1])), picks))

    dec, notes = {}, {}
    for x, k, r in sorted(parsed, key=lambda t: t[0]["rcept_no"]):       # 접수번호 순 → 정정공시가 뒤에서 덮어씀
        if not r or not r.get("record"):
            continue
        ev = {**r, "rcept_no": x["rcept_no"], "filed": f"{x['rcept_dt'][:4]}-{x['rcept_dt'][4:6]}-{x['rcept_dt'][6:]}",
              "title": x.get("report_nm", "").strip()}
        ev["slot"] = slot_of(r.get("kind", ""), r["record"])
        (dec if k == "d" else notes)[(ev["slot"], r["record"])] = ev
    events = sorted(dec.values(), key=lambda e: e["record"])

    # 같은 배당끼리 평균
    slots = []
    for s in ("Q1", "Q2", "H", "Q3", "Y", "Q4"):
        es = [e for e in events if e["slot"] == s]
        if not es:
            continue
        lags = [(_d(e["pay"]) - _d(e["record"])).days for e in es if e.get("pay")]
        recent = es[-3:]
        mon = max({int(e["record"][5:7]) for e in recent}, key=lambda m: (sum(int(e["record"][5:7]) == m for e in recent),
                                                                          max(e["record"] for e in recent if int(e["record"][5:7]) == m)))
        last = [e for e in es if int(e["record"][5:7]) == mon][-1]
        pays = [e["pay"] for e in es if e.get("pay")]
        slots.append({
            "slot": s, "name": SLOT_NAME[s], "years": len({e["record"][:4] for e in es}),
            "record_md": last["record"][5:], "record_month": mon,
            "pay_month_avg": round(_avg([_month_pos(p) for p in pays]), 1) if pays else None,
            "lag_avg": round(_avg(lags)) if lags else None,
            "dps_avg": round(_avg([e.get("dps") for e in es]) or 0) or None,
            "dps_last": last.get("dps"), "dps_hist": [[e["record"][:7], e.get("dps")] for e in es],
            "moved": len({int(e["record"][5:7]) for e in es}) > 1,
        })
        if slots[-1]["lag_avg"] is None and s == "Y" and mon == 12:
            slots[-1]["lag_avg"], slots[-1]["lag_guess"] = 115, True   # 지급일이 공시에 한 번도 없으면: 12월 기준일 → 주총(3월) 뒤 4월 지급이 일반적이라 4월 하순으로 잡음

    # 다가오는 일정: 확정(공시) → 없으면 예상
    up = []
    for sl in slots:
        s = sl["slot"]
        conf = [e for e in events if e["slot"] == s and (e["record"] >= today.isoformat() or (e.get("pay") or "") >= today.isoformat())]
        note = sorted([n for n in notes.values() if n["slot"] == s and n["record"] >= today.isoformat()
                       and not any(e["record"] == n["record"] for e in events)], key=lambda n: n["record"])
        if conf:
            e = conf[0]
            up.append(_plan(sl, e["record"], e.get("pay"), e.get("dps"), "확정", today, e))
        elif note:
            n = note[0]
            pay = (_d(n["record"]) + dt.timedelta(days=sl["lag_avg"])).isoformat() if sl["lag_avg"] else None
            up.append(_plan(sl, n["record"], pay, None, "기준일 공시", today, n))
        else:
            last = max(e["record"] for e in events if e["slot"] == s)
            y = int(last[:4]) + 1
            while True:
                rec = _md(y, sl["record_md"], sl["record_month"])
                pay = (rec + dt.timedelta(days=sl["lag_avg"])).isoformat() if sl["lag_avg"] else None
                if rec >= today or (pay and pay >= today.isoformat()):
                    break
                y += 1
            up.append(_plan(sl, rec.isoformat(), pay, None, "예상", today, None))
    up.sort(key=lambda u: u["record"])
    return {"code": code, "name": corp.get("name"), "events": events[::-1], "slots": slots, "upcoming": up,
            "asof": today.isoformat(), "none": not events}


# ── 시장 전체: 곧 기준일이 오는 배당 (최근 공시 기준) ─────────────────────
UP_FILE = ds.CACHE / "div_upcoming.json"
UP_BACK = 75                                           # 며칠 전 공시까지 볼지 (DART는 회사 지정 없이 3개월까지만 검색됨)
UP_TTL = 6 * 3600
_up_lock = threading.Lock()
_up_busy = 0.0


def _list_market(cls: str, bgn: str, end: str) -> list[dict]:
    """한 시장(Y 코스피 · K 코스닥)의 거래소공시 목록에서 배당 결정·기준일 설정만"""
    out, page = [], 1
    while page <= 150:
        j = requests.get("https://opendart.fss.or.kr/api/list.json", timeout=20,
                         params={"crtfc_key": _key(), "bgn_de": bgn, "end_de": end, "pblntf_ty": "I", "corp_cls": cls,
                                 "page_no": page, "page_count": 100}).json()
        if j.get("status") == "013":
            break
        if j.get("status") != "000":
            raise RuntimeError(f"DART {j.get('status')}: {j.get('message')}")
        for x in j.get("list") or []:
            nm = x.get("report_nm", "")
            if x.get("stock_code") and (RX_DECIDE.search(nm) or RX_RECORD.search(nm)):
                out.append({**x, "_mkt": "코스피" if cls == "Y" else "코스닥"})
        if page >= int(j.get("total_page") or 1):
            break
        page += 1
    return out


def build_upcoming(today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    bgn, end = (today - dt.timedelta(days=UP_BACK)).strftime("%Y%m%d"), today.strftime("%Y%m%d")
    lst = _list_market("Y", bgn, end) + _list_market("K", bgn, end)
    picks = [(x, "d" if RX_DECIDE.search(x.get("report_nm", "")) else "r") for x in lst]
    with ThreadPoolExecutor(6) as ex:
        parsed = list(ex.map(lambda p: (p[0], p[1], _safe_doc(p[0]["rcept_no"], p[1])), picks))
    dec, notes = {}, {}
    for x, k, r in sorted(parsed, key=lambda t: t[0]["rcept_no"]):      # 접수번호 순 → 정정공시가 뒤에서 덮어씀
        if not r or not r.get("record"):
            continue
        slot = slot_of(r.get("kind", ""), r["record"])
        (dec if k == "d" else notes)[(x["stock_code"], slot)] = (x, k, r, slot)
    items = []
    for (code, slot), (x, k, r, _s) in {**notes, **dec}.items():        # 결정 공시가 있으면 그쪽(금액·지급일이 있음)
        rec = _d(r["record"])
        if rec < today:
            continue
        lb, exd = buy_deadline(rec)
        if lb < today:                                                   # 이미 마지막 매수일이 지남
            continue
        items.append({
            "code": code, "name": (x.get("corp_name") or "").strip(), "market": x["_mkt"],
            "slot": slot, "slot_name": SLOT_NAME.get(slot, ""), "status": "확정" if k == "d" else "기준일 공시",
            "record": r["record"], "pay": r.get("pay"), "dps": r.get("dps"), "yield": r.get("yield"),
            "buy_by": lb.isoformat(), "ex_date": exd.isoformat(), "days_left": (lb - today).days,
            "cal_sure": rec <= HOLIDAY_SURE_UNTIL, "rcept_no": x["rcept_no"],
            "filed": f"{x['rcept_dt'][:4]}-{x['rcept_dt'][4:6]}-{x['rcept_dt'][6:]}",
        })
    items.sort(key=lambda i: (i["buy_by"], -(i.get("yield") or 0)))
    return {"asof": today.isoformat(), "ts": time.time(), "back_days": UP_BACK, "items": items}


def upcoming() -> dict:
    """저장된 목록을 바로 돌려주고, 6시간이 지났으면 뒤에서 새로 모음 (처음엔 1~2분 걸려서 기다리게 하지 않음)"""
    global _up_busy
    try:
        cur = json.loads(UP_FILE.read_text())
    except Exception:
        cur = None
    fresh = cur and time.time() - cur.get("ts", 0) < UP_TTL and cur.get("asof") == dt.date.today().isoformat()
    if not fresh:
        with _up_lock:
            start = time.time() - _up_busy > 900
            if start:
                _up_busy = time.time()
        if start:
            def work():
                global _up_busy
                try:
                    UP_FILE.write_text(json.dumps(build_upcoming(), ensure_ascii=False))
                    UP_FILE.with_suffix(".err").unlink(missing_ok=True)
                except Exception as e:
                    print("dividend upcoming", type(e).__name__, str(e)[:200], flush=True)
                    try:
                        UP_FILE.with_suffix(".err").write_text(f"{type(e).__name__}: {str(e)[:200]}")
                    except Exception:
                        pass
                _up_busy = 0.0
            threading.Thread(target=work, daemon=True).start()
    out = dict(cur) if cur else {"items": []}
    if cur and cur.get("asof") != dt.date.today().isoformat():           # 어제 목록이면 지난 것만 걸러서 보여 줌
        t = dt.date.today()
        out["items"] = [{**i, "days_left": (_d(i["buy_by"]) - t).days} for i in cur["items"] if i["buy_by"] >= t.isoformat()]
    out["loading"] = not fresh
    out["collecting"] = _up_busy > 0                                       # 지금 뒤에서 모으는 중인지
    if not fresh and not out["collecting"]:                               # 모으다 실패했으면 이유를 화면에 보여 줌
        try:
            out["error"] = UP_FILE.with_suffix(".err").read_text()
        except Exception:
            pass
    return out


def _plan(sl, record, pay, dps, status, today, src):
    rec = _d(record)
    p = {"slot": sl["slot"], "name": sl["name"], "status": status, "record": record,
         "pay": pay, "pay_est": status != "확정" or not pay,
         "dps": dps if dps is not None else sl["dps_last"], "dps_est": dps is None,
         "rcept_no": src and src.get("rcept_no"), "filed": src and src.get("filed")}
    if status == "확정" and not pay and sl["lag_avg"]:
        p["pay"] = (rec + dt.timedelta(days=sl["lag_avg"])).isoformat()
    if rec >= today:
        lb, ex = buy_deadline(rec)
        p.update(buy_by=lb.isoformat(), ex_date=ex.isoformat(), days_left=(lb - today).days,
                 cal_sure=rec <= HOLIDAY_SURE_UNTIL)
    else:
        p["passed"] = True                              # 기준일은 지났고 지급만 남음
    return p


def _safe_doc(rno, kind):
    try:
        return _doc(rno, kind)
    except Exception as e:
        print("dividend doc", rno, type(e).__name__, str(e)[:100], flush=True)
        return None


def _d(s):
    return dt.date.fromisoformat(s)


def _month_pos(s):
    d = _d(s)
    return d.month + (d.day - 1) / 31


def _md(y, md, mon):
    m, d = int(md[:2]), int(md[3:])
    while True:
        try:
            return dt.date(y, m, d)
        except ValueError:
            d -= 1                                     # 2/29 → 2/28


if __name__ == "__main__":
    a = sys.argv[1] if len(sys.argv) > 1 else "005930"
    print(json.dumps(build_upcoming() if a == "upcoming" else build(a), ensure_ascii=False, indent=1))
