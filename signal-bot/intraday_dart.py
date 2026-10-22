"""
intraday_dart.py — 장중 공시 알림: 백테스트로 효과가 확인된 공시만 (코스피)

cron-job.org가 평일 장중 5분마다 GitHub Actions(workflow_dispatch)를 깨우면 실행된다.
오늘 접수된 원공시(정정 제외) 중 2015~2026 백테스트에서 두 기간(2015~2020, 2021~2026) 모두 유의했던 것만 알린다.
  - 자사주 신탁계약·취득결정: 코스피 전체, 20일 평균 거래대금 3억 원 이상 (효과는 30억 미만 중소형에서 가장 큼)
  - 단일판매·공급계약: 주가가 200일선 위일 때만, 거래대금 3억 원 이상
(무상증자·액면분할·소각·잠정실적·배당은 표본이 적거나 최근 효과가 약해 제외. backtest/research/README.md 4차)

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
    ("자사주 신탁계약", r"자기주식취득신탁계약체결결정",
     "공시 다음 날 매수 시 20일 +1.9%(2015~20)·+2.1%(2021~), 거래대금 30억 미만은 +2~4%"),
    ("자사주 취득",     r"^(주요사항보고서\()?자기주식취득결정",
     "20일 +1.5%(2015~20)·+1.9%(2021~), 거래대금 30억 미만은 +2~3%"),
    ("공급계약",        r"단일판매ㆍ공급계약체결",
     "200일선 위 종목 60일 +2.8%(2015~20)·+3.9%(2021~), 승률 42~45%(일부 급등이 평균을 끌어올림)"),
]
LIQ = 3e8


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
        # 표준 표: 매출액 당해실적 [당기, 전기, 전기대비%, 흑자전환여부, 전년동기, 전년동기대비%, 여부]
        s, good = [], None
        for lab in ("매출액", "영업이익"):
            m = re.search(re.escape(lab) + r"\s*당해실적((?:\s+\S+){7})", text)
            if not m:
                continue
            tok = m.group(1).split()
            try:
                yoy = float(tok[5].replace(",", "").replace("%", ""))
            except ValueError:
                continue                    # '-' 만 있는 월별 매출 공시 등
            s.append(f"{lab} 전년동기 대비 {yoy:+.1f}%")
            if lab == "매출액":
                good = yoy > 10
            elif good is not False:
                good = bool(good) or yoy > 20
        return (good if s else False, ", ".join(s))   # 수치가 없으면(월별 매출 등) 알리지 않음
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


def dps_of(text: str):
    m = re.search(r"1주당\s*배당금\s*\(원\)\s*보통주식\s*" + NUM, text)
    return float(m.group(1).replace(",", "")) if m else None


def dividend(e, text: str, key: str, day: str):
    """이번 주당배당금을 작년 같은 시기(300~430일 전) 배당결정과 비교. 늘었을 때만 호재."""
    now_dps = dps_of(text)
    yld = re.search(r"시가배당률\s*\(%\)\s*보통주식\s*" + NUM, text)
    yl = f", 시가배당률 {float(yld.group(1)):.2f}%" if yld else ""
    if now_dps is None:
        return (None, "")
    d0 = datetime.strptime(day, "%Y%m%d")
    try:
        j = requests.get(f"{DART}/list.json", params={
            "crtfc_key": key, "corp_code": e["corp_code"], "pblntf_ty": "I",
            "bgn_de": (d0 - timedelta(days=430)).strftime("%Y%m%d"), "end_de": (d0 - timedelta(days=300)).strftime("%Y%m%d"),
            "page_count": 100}, timeout=30).json()
        prev = [it for it in j.get("list", []) if re.search(r"^(현금ㆍ현물배당결정|현금배당결정)", re.sub(r"\s+", "", it["report_nm"]))]
    except Exception:
        prev = []
    if not prev:
        return (None, f"주당 {now_dps:,.0f}원{yl} · 작년 비교 불가")
    p = min(prev, key=lambda it: abs((datetime.strptime(it["rcept_dt"], "%Y%m%d") - (d0 - timedelta(days=365))).days))
    old = dps_of(doc_text(p["rcept_no"], key))
    if not old:
        return (None, f"주당 {now_dps:,.0f}원{yl} · 작년 비교 불가")
    chg = now_dps / old - 1
    return (chg > 0.001, f"주당 {now_dps:,.0f}원 (작년 같은 시기 {old:,.0f}원, {chg:+.0%}){yl}")


def _n(x):
    return float(x.replace(",", ""))


def bb_parse(kind: str, t: str) -> dict:
    """자사주 취득결정·신탁계약 원문에서 항목을 뽑는다(못 찾은 항목은 키 없음)."""
    d = {}
    if not t:
        return d
    tr = "신탁" in kind
    m = re.search(r"계약금액\s*\(원\)\s*" + NUM, t) if tr else re.search(r"취득예(?:상|정)금액\s*\(원\)\s*보통주식\s*" + NUM, t)
    if m and _n(m.group(1)) > 0:
        d["amount"] = _n(m.group(1))
    m = re.search(r"취득예정주식\s*(?:수)?\s*\(주\)\s*보통주식\s*" + NUM, t)
    if m and _n(m.group(1)) > 0:
        d["shares"] = _n(m.group(1))
    m = re.search(r"(?:취득예상기간|계약기간)\s*시작일\s*(\d{4})\D+(\d{1,2})\D+(\d{1,2})\D+종료일\s*(\d{4})\D+(\d{1,2})\D+(\d{1,2})", t)
    if m:
        g = [int(x) for x in m.groups()]
        d["period"] = f"{g[0]}.{g[1]:02d}.{g[2]:02d}~{g[3]}.{g[4]:02d}.{g[5]:02d}"
    m = re.search(r"(?:취득|계약)\s*목적\s*(.{2,70}?)(?=\s*(?:\d+\.|취득방법|계약체결|기타|$))", t)
    if m:
        d["purpose"] = m.group(1).strip(" :-")
    m = re.search(r"취득방법\s*(.{2,40}?)\s*(?=\d+\.\s*위탁)", t)
    if m:
        d["method"] = m.group(1).strip(" :-")
    m = re.search(r"위탁투자중개업자\s*(.{2,80}?)\s*(?=\d+\.\s)", t)
    if m:
        d["broker"] = re.sub(r"\s*\([^)]*\)", "", m.group(1)).strip(" :-,")
    m = re.search(r"계약체결기관\s*(.{2,60}?)\s*(?=\d+\.\s)", t)
    if m and "broker" not in d:
        d["broker"] = re.sub(r"\s*\([^)]*\)", "", m.group(1)).strip(" :-,")
    # 취득(계약) 전 자기주식 보유현황: 배당가능이익 범위 내 취득 + 기타취득
    m = re.search(r"(?:취득|계약)\s*전\s*자기주식\s*보유현황\s*(.{0,300}?)\d+\.\s*(?:취득결정일|이사회결의일)", t)
    if m:
        seg, sh, pc = m.group(1), 0.0, 0.0
        for mm in re.finditer(r"\(주\)\s*보통주식\s*" + NUM + r"\s*비율\s*\(%\)\s*" + NUM, seg):
            sh += _n(mm.group(1)); pc += _n(mm.group(2))
        for mm in re.finditer(r"\(주\)\s*보통주식\s*-\s*비율", seg):
            pass
        d["held"] = (sh, pc)
    if "전량 소각" in t or "소각 예정" in t or "소각할 예정" in t:
        d["burn"] = True
    return d


def bb_lines(kind: str, d: dict, price=None) -> list:
    tr = "신탁" in kind
    L = []
    if d.get("shares"):
        L.append(f"▪ 취득 예정 수량: 보통주 {d['shares']:,.0f}주")
    if d.get("amount"):
        a = d["amount"]
        L.append(f"▪ {'계약' if tr else '취득 예정'} 금액: {a:,.0f}원 (약 {a / 1e8:,.0f}억원)" if a >= 1e8 else f"▪ {'계약' if tr else '취득 예정'} 금액: {a:,.0f}원")
    if d.get("purpose"):
        L.append(f"▪ {'계약' if tr else '취득'} 목적: {d['purpose']}" + (" (소각 예정)" if d.get("burn") and "소각" not in d["purpose"] else ""))
    if d.get("method"):
        L.append(f"▪ 취득 방법: {d['method']}")
    if d.get("period"):
        L.append(f"▪ {'계약' if tr else '취득 예정'} 기간: {d['period']}")
    if d.get("broker"):
        L.append(f"▪ {'계약 체결 기관' if tr else '매수 위탁'}: {d['broker']}")
    if d.get("held"):
        sh, pc = d["held"]
        L.append(f"▪ 기존 자기주식 보유: {sh:,.0f}주 ({pc:.2f}%)" if sh else "▪ 기존 자기주식 보유: 없음")
    return L


def buyback_detail(kind: str, text: str) -> str:
    return " · ".join(l[2:] for l in bb_lines(kind, bb_parse(kind, text)))


def buyback_digest(day: str, rows, key: str, now) -> str:
    """오늘 접수된 코스피 자사주 취득·신탁체결 공시 전체(거래대금 필터 없이)."""
    items = []
    for it in rows:
        nm = re.sub(r"\s+", "", it.get("report_nm", ""))
        if not it.get("stock_code") or not it["stock_code"].endswith("0"):
            continue
        for kind, pat, _ in TYPES[:2]:
            if re.search(pat, nm):
                tag = "정정 " if nm.startswith("[") else ""
                items.append((it, kind, tag))
                break
    head = f"📋 오늘의 자사주 매입 공시 · {day[4:6]}/{day[6:]}"
    if not items:
        return head + "\n\n오늘 코스피 자사주 취득·신탁계약 공시는 없었습니다."
    L = [head, f"코스피 {len(items)}건 (정정 포함, 거래대금 필터 없음)", ""]
    for it, kind, tag in items:
        dl = bb_lines(kind, bb_parse(kind, doc_text(it["rcept_no"], key))) if not tag else []
        time.sleep(0.3)
        L.append(f"■ {it.get('corp_name', it['stock_code'])} ({it['stock_code']}) — {tag}{kind}")
        L += dl
        L.append(f"  https://dart.fss.or.kr/dsaf001/main.do?rcpNo={it['rcept_no']}")
        L.append("")
    return "\n".join(L)


def broadcast(text: str):
    send(text)
    for gchat in [g.strip() for g in os.environ.get("GROUP_CHAT_ID", "").split(",") if g.strip()]:
        os.environ["TELEGRAM_CHAT_ID"] = gchat
        try:
            send(text)
        except SystemExit as ex:
            print("::warning::그룹 전송 실패", ex)


def quote(code: str):
    info = {}
    try:
        j = requests.get(f"https://m.stock.naver.com/api/stock/{code}/basic", headers=UA, timeout=10).json()
        info["price"] = float(str(j.get("closePrice", "")).replace(",", "") or "nan")
        info["chg"] = float(j.get("fluctuationsRatio") or "nan")
    except Exception:
        pass
    try:
        d = daily(code, (datetime.now(KST) - timedelta(days=330)).strftime("%Y%m%d"))
        c = d["Close"]
        info["tv20"] = float((c * d["Volume"]).iloc[-21:-1].mean())          # 오늘(미완성) 제외
        info["rsi"] = float(rsi(c).iloc[-1])
        if len(c) >= 201:
            info["above200"] = bool(c.iloc[-1] > c.iloc[-201:-1].mean())
    except Exception:
        pass
    return info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--any-time", action="store_true", help="시간 제한 없이 실행(시험용)")
    ap.add_argument("--date", help="YYYYMMDD (시험용, 기본 오늘)")
    ap.add_argument("--dump-doc", help="자사주 공시 원문의 항목 부분 출력(파서 점검용)")
    ap.add_argument("--show-doc", help="접수번호 원문 텍스트 일부 출력(파서 점검용)")
    a = ap.parse_args()
    if a.dump_doc:
        t = doc_text(a.dump_doc, (os.environ.get("DART_API_KEY") or "").strip())
        i = max(t.find("취득예정주식"), t.find("계약금액"), 0)
        print(f"[{a.dump_doc}] 길이 {len(t)}\n본문: {t[max(0, i - 100):i + 1800]}")
        for kw in ("보유현황", "보유비율", "지분율"):
            j = t.find(kw)
            print(f"--{kw}: {t[max(0, j - 150):j + 500] if j >= 0 else '없음'}")
        return
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

    rows = dart_list(day, "B", key) + dart_list(day, "I", key)
    fresh = []
    for it in rows:
        code, no = it.get("stock_code"), it["rcept_no"]
        nm = re.sub(r"\s+", "", it.get("report_nm", ""))
        if not code or not code.endswith("0") or no in done or nm.startswith("["):
            continue
        for kind, pat, why in TYPES:
            if re.search(pat, nm):
                fresh.append({"code": code, "name": it.get("corp_name", code), "kind": kind, "why": why, "rcept_no": no,
                              "corp_code": it.get("corp_code")})
                break
    print(f"{day} 대상 유형 새 공시 {len(fresh)}건")

    picks, others = [], []
    for e in fresh:
        q = quote(e["code"])
        e["q"] = q
        tv = q.get("tv20")
        is_bb = e["kind"].startswith("자사주")
        if (tv is None or tv < LIQ) and not is_bb:
            print("제외(거래대금 부족)", e["name"], tv); continue
        e["summary"] = (f"20일 거래대금 {tv / 1e8:,.0f}억" if tv else "거래대금 확인 불가") + (" · 유동성 낮음(참고)" if is_bb and (tv or 0) < LIQ else "")
        if is_bb:
            e["bb"] = bb_lines(e["kind"], bb_parse(e["kind"], doc_text(e["rcept_no"], key)))
            time.sleep(0.3)
        if e["kind"] == "공급계약":
            if not q.get("above200"):
                print("제외(200일선 아래)", e["name"]); continue
            _, summ = analyze("공급계약", doc_text(e["rcept_no"], key))
            time.sleep(0.3)
            if summ:
                e["summary"] = summ + " · " + e["summary"]
        picks.append(e)
    if picks:
        L = [f"⚡ 장중 공시 알림 · {now:%m/%d %H:%M}" + ("" if day == now.strftime("%Y%m%d") else f" · {day}"), ""]
        for title, group in (("🟢 백테스트 검증 공시", picks),):
            if not group:
                continue
            L.append(title)
            for e in group:
                q = e["q"]
                px = f"{q['price']:,.0f}원 ({q['chg']:+.1f}%)" if q.get("price") == q.get("price") and "price" in q else ""
                r = f" · RSI {q['rsi']:.0f}" if "rsi" in q else ""
                if e.get("bb") is not None:
                    L.append(f"■ {e['name']} ({e['code']}) — {e['kind']}결정")
                    L.append(f"▪ 확인 시각: {now:%H:%M} (공시 접수일 {day[4:6]}/{day[6:]})")
                    L += e["bb"]
                    L.append(f"▪ {e['summary']}")
                else:
                    L.append(f"• {e['name']} — {e['kind']}" + (f" ({e['summary']})" if e["summary"] else ""))
                if px or r:
                    L.append(f"  {px}{r}")
                L.append(f"  근거: {e['why']}")
                L.append(f"  https://dart.fss.or.kr/dsaf001/main.do?rcpNo={e['rcept_no']}")
            L.append("")
        L.append("※ 수치는 공시 다음 날 시가 매수 기준 유사 종목 대비 평균 초과수익(과거 성과이며 보장 아님). 자사주는 모의투자 B에 다음 날 시가 매수로 기록됩니다.")
        text = "\n".join(L)
        print(text)
        has_alert = bool(picks)
        if has_alert and not a.dry_run:
            broadcast(text)
    # 하루 1회: 오늘 자사주 매입 공시 전체 요약(0건이어도 "없음"으로 알림) — 18시 이후 첫 실행
    if (a.any_time or (now.weekday() < 5 and now.hour >= 18)) and "DIGEST" not in done:
        dg = buyback_digest(day, rows, key, now)
        print(dg)
        if not a.dry_run:
            broadcast(dg)
            done.add("DIGEST")
    if not a.dry_run:
        seen[day] = sorted(done | {e["rcept_no"] for e in fresh})
        with open(SEEN, "w", encoding="utf-8") as f:
            json.dump(seen, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
