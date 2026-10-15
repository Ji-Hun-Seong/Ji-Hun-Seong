"""
intraday_dart.py — 장중 호재 공시 알림 (코스피200 종목)

cron-job.org가 평일 장중 5분마다 GitHub Actions(workflow_dispatch)를 깨우면 실행된다.
오늘 접수된 코스피200 종목의 원공시(정정 제외) 중 주가에 긍정적일 만한 것을 골라 텔레그램으로 알린다.
  - 자사주 취득·신탁계약, 자사주 소각, 무상증자, 액면분할, 현금배당 결정
  - 단일판매·공급계약 (원문에서 계약금액·매출액 대비 % 추출)
  - 영업(잠정)실적, 매출액·손익구조 30%(대규모 15%) 이상 변경 (원문에서 매출·영업이익 증감률 추출 → 증가한 경우만)
알림마다 2014~2026 백테스트(backtest/research/README.md 4차)의 근거 강도를 함께 적는다.

    python signal-bot/intraday_dart.py                     # 오늘 확인 + 전송 + 본 공시 기록
    python signal-bot/intraday_dart.py --date 20261013 --dry-run --any-time   # 지난 날짜 시험
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
import zipfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from daily_signals import DART, UA, daily, rsi, send  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SEEN = os.path.join(HERE, "intraday_seen.json")
KST = ZoneInfo("Asia/Seoul")

# (이름, 정규식, 근거) — 근거는 공시 다음 날 시가 매수 기준, 유사 종목 대비 초과수익(2015~2026)
TYPES = [
    ("자사주 신탁계약", r"자기주식취득신탁계약체결결정", "중소형주 20일 +2~4%(유의). 대형주는 효과 약함"),
    ("자사주 취득",     r"^(주요사항보고서\()?자기주식취득결정", "중소형주 20일 +2~3%(유의). 대형주는 효과 약함"),
    ("자사주 소각",     r"주식소각결정", "효과 확인 안 됨(참고용)"),
    ("무상증자",        r"^(주요사항보고서\()?무상증자결정", "20일 +2~3%, 표본 적어 유의성 약함"),
    ("액면분할",        r"주식분할결정", "60일 +7~8%, 표본 적어 유의성 약함"),
    ("현금배당 결정",   r"현금ㆍ현물배당결정|현금배당결정", "배당 20%↑ 증가 시 과거엔 60일 +3%, 최근 약해짐"),
    ("공급계약",        r"단일판매ㆍ공급계약체결", "대형주 60일 +3.2%(유의), 승률 45%"),
    ("잠정실적",        r"영업\(잠정\)실적", "실적 공시 전체로는 효과 없음 — 증가폭 큰 경우만 참고"),
    ("손익구조 변경",   r"매출액또는손익구조", "증가 공시만 참고(별도 검증 전)"),
]


def kospi200() -> dict[str, str]:
    out = {}
    for page in range(1, 16):
        r = requests.get("https://m.stock.naver.com/api/index/KPI200/enrollStocks",
                         params={"page": page, "pageSize": 20}, headers=UA, timeout=20)
        items = r.json()
        items = items.get("stocks", items) if isinstance(items, dict) else items
        new = {it["itemCode"]: it.get("stockName", "") for it in items if it.get("itemCode") not in out}
        if not new:
            break
        out.update(new)
    return out


def dart_list(day: str, ty: str, key: str):
    out, page = [], 1
    while True:
        j = requests.get(f"{DART}/list.json", params={
            "crtfc_key": key, "corp_cls": "Y", "pblntf_ty": ty, "bgn_de": day, "end_de": day,
            "page_no": page, "page_count": 100}, timeout=30).json()
        if j.get("status") == "013":
            break
        if j.get("status") != "000":
            raise RuntimeError(f"DART {j.get('status')} {j.get('message')}")
        out += j.get("list", [])
        if page >= int(j.get("total_page", 1)):
            break
        page += 1
        time.sleep(0.2)
    return out


def doc_text(rcept_no: str, key: str) -> str:
    """공시 원문(zip 안 XML/HTML)을 태그 없는 텍스트로."""
    try:
        r = requests.get(f"{DART}/document.xml", params={"crtfc_key": key, "rcept_no": rcept_no}, timeout=30)
        z = zipfile.ZipFile(io.BytesIO(r.content))
        raw = " ".join(z.read(n).decode("utf-8", "ignore") for n in z.namelist())
    except Exception as e:
        print("원문 실패", rcept_no, e)
        return ""
    t = re.sub(r"<[^>]+>", " ", raw)
    t = re.sub(r"&nbsp;|&#160;", " ", t)
    return re.sub(r"\s+", " ", t)


NUM = r"(-?[\d,]+(?:\.\d+)?)"


def nums_after(text: str, label: str, n: int, skip: str = ""):
    """label 뒤에 오는 숫자 n개(쉼표 제거). skip은 label과 숫자 사이에 끼는 단어(예: '당해실적')."""
    m = re.search(re.escape(label) + r"\s*(?:\(원\))?\s*" + (re.escape(skip) + r"\s*" if skip else "") +
                  r"\s*".join([NUM] * n), text)
    if not m:
        return None
    try:
        return [float(x.replace(",", "")) for x in m.groups()]
    except ValueError:
        return None


def analyze(kind: str, text: str):
    """(호재 여부, 요약 문자열). 판단 불가면 (None, '')."""
    if kind == "공급계약":
        amt = re.search(r"계약금액(?:\s*\(원\))?\s*" + NUM, text)
        pct = re.search(r"매출액\s*대비\s*\(?%\)?\s*" + NUM, text)
        s = []
        if amt:
            s.append(f"계약금액 {float(amt.group(1).replace(',', '')) / 1e8:,.0f}억")
        if pct:
            p = float(pct.group(1).replace(",", ""))
            s.append(f"최근 매출 대비 {p:.1f}%")
            return (p >= 5, ", ".join(s))
        return (None, ", ".join(s))
    if kind == "잠정실적":
        s, good = [], None
        for lab in ("매출액", "영업이익"):
            v = nums_after(text, lab, 5, "당해실적")      # 당기, 전기, 전기대비%, 전년동기, 전년동기대비%
            if v:
                s.append(f"{lab} 전년동기 대비 {v[4]:+.1f}%")
                if lab == "매출액":
                    good = v[4] > 10
                elif good is not False:
                    good = good or v[4] > 20
        return (good, ", ".join(s))
    if kind == "손익구조 변경":
        s, good = [], None
        for lab in ("매출액", "영업이익"):
            v = nums_after(text, "- " + lab, 4) or nums_after(text, lab, 4)   # 당해, 직전, 증감금액, 증감비율
            if v:
                s.append(f"{lab} {v[3]:+.1f}%")
                if lab == "매출액":
                    good = v[3] > 0
                elif good is not False:
                    good = good or v[3] > 0
        return (good, ", ".join(s))
    return (True, "")


def quote(code: str):
    info = {}
    try:
        j = requests.get(f"https://m.stock.naver.com/api/stock/{code}/basic", headers=UA, timeout=10).json()
        info["price"] = float(str(j.get("closePrice", "")).replace(",", "") or "nan")
        info["chg"] = float(j.get("fluctuationsRatio") or "nan")
    except Exception:
        pass
    try:
        d = daily(code, (datetime.now(KST) - timedelta(days=90)).strftime("%Y%m%d"))
        info["rsi"] = float(rsi(d["Close"]).iloc[-1])
    except Exception:
        pass
    return info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--any-time", action="store_true", help="시간 제한 없이 실행(시험용)")
    ap.add_argument("--date", help="YYYYMMDD (시험용, 기본 오늘)")
    ap.add_argument("--show-doc", help="접수번호 원문 텍스트 일부 출력(파서 점검용)")
    a = ap.parse_args()
    if a.show_doc:
        t = doc_text(a.show_doc, (os.environ.get("DART_API_KEY") or "").strip())
        i = max(t.find("매출액"), 0)
        print(f"[{a.show_doc}] 길이 {len(t)}\n앞부분: {t[:400]}\n매출액 주변: {t[max(0, i - 200):i + 900]}\n배당 주변: {t[max(0, t.find('1주당')):t.find('1주당') + 600]}")
        return
    now = datetime.now(KST)
    if not a.any_time and (now.weekday() >= 5 or not (7 <= now.hour < 19)):
        print(f"KST {now:%a %H:%M} — 평일 07~19시에만 확인합니다.")
        return
    key = (os.environ.get("DART_API_KEY") or "").strip()
    if not key:
        sys.exit("::error::DART_API_KEY 없음")
    day = a.date or now.strftime("%Y%m%d")
    seen = json.load(open(SEEN, encoding="utf-8")) if os.path.exists(SEEN) else {}
    seen = {k: v for k, v in seen.items() if k >= (now - timedelta(days=7)).strftime("%Y%m%d")}
    done = set(seen.get(day, [])) if not a.dry_run else set()

    k200 = kospi200()
    if len(k200) < 150:
        sys.exit(f"::error::코스피200 목록 {len(k200)}개 — 네이버 응답 확인 필요")
    rows = dart_list(day, "B", key) + dart_list(day, "I", key)
    fresh = []
    for it in rows:
        code, no = it.get("stock_code"), it["rcept_no"]
        nm = re.sub(r"\s+", "", it.get("report_nm", ""))
        if code not in k200 or no in done or nm.startswith("["):
            continue
        for kind, pat, why in TYPES:
            if re.search(pat, nm):
                fresh.append({"code": code, "name": k200[code], "kind": kind, "why": why, "rcept_no": no})
                break
    print(f"{day} 코스피200 관련 새 공시 {len(fresh)}건")

    picks, others = [], []
    for e in fresh:
        good, summ = (True, "")
        if e["kind"] in ("공급계약", "잠정실적", "손익구조 변경"):
            good, summ = analyze(e["kind"], doc_text(e["rcept_no"], key))
            time.sleep(0.3)
        e["summary"] = summ
        (picks if good else others).append(e) if good is not None else others.append(e)
        if good is None:
            e["summary"] = (summ + " · " if summ else "") + "원문 수치 확인 필요"
    if picks or others:
        L = [f"⚡ 장중 공시 알림 (코스피200) · {now:%m/%d %H:%M}" + ("" if day == now.strftime("%Y%m%d") else f" · {day}"), ""]
        for title, group in (("🟢 호재 공시", picks), ("⚪ 확인 필요(수치 미확인·감소)", [o for o in others if "확인 필요" in o["summary"]])):
            if not group:
                continue
            L.append(title)
            for e in group:
                q = quote(e["code"])
                px = f"{q['price']:,.0f}원 ({q['chg']:+.1f}%)" if q.get("price") == q.get("price") and "price" in q else ""
                r = f" · RSI {q['rsi']:.0f}" if "rsi" in q else ""
                L.append(f"• {e['name']} — {e['kind']}" + (f" ({e['summary']})" if e["summary"] else ""))
                if px or r:
                    L.append(f"  {px}{r}")
                L.append(f"  근거: {e['why']}")
                L.append(f"  https://dart.fss.or.kr/dsaf001/main.do?rcpNo={e['rcept_no']}")
            L.append("")
        L.append("※ 참고용 알림입니다. 모의투자 B는 검증된 규칙(자사주 공시 → 다음 날 시가)대로 따로 기록합니다.")
        text = "\n".join(L)
        print(text)
        has_alert = bool(picks) or any("확인 필요" in o["summary"] for o in others)
        if has_alert and not a.dry_run:
            send(text)
            gchat = os.environ.get("GROUP_CHAT_ID", "").strip()
            if gchat:
                os.environ["TELEGRAM_CHAT_ID"] = gchat
                try:
                    send(text)
                except SystemExit as ex:
                    print("::warning::그룹 전송 실패", ex)
    if not a.dry_run:
        seen[day] = sorted(done | {e["rcept_no"] for e in fresh})
        with open(SEEN, "w", encoding="utf-8") as f:
            json.dump(seen, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
