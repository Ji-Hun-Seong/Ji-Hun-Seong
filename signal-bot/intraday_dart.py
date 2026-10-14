"""
intraday_dart.py — 장중 자사주 공시 실시간 알림

cron-job.org가 평일 장중 5분마다 GitHub Actions(workflow_dispatch)를 깨우면 실행된다.
오늘 접수된 코스피 자사주 취득결정·신탁계약체결 원공시 중 처음 보는 것을 텔레그램으로 알린다.
(모의 포트폴리오는 백테스트와 같은 규칙대로 저녁 일일 봇이 '다음 날 시가 매수'로 기록한다)

    python signal-bot/intraday_dart.py            # 확인 + 전송 + 본 공시 기록
    python signal-bot/intraday_dart.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from daily_signals import BUYBACK, BB_LIQ, DART, UA, daily, rsi, send  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SEEN = os.path.join(HERE, "intraday_seen.json")
KST = ZoneInfo("Asia/Seoul")


def todays_buybacks(day: str):
    key = (os.environ.get("DART_API_KEY") or "").strip()
    if not key:
        sys.exit("::error::DART_API_KEY 없음")
    out, page = [], 1
    while True:
        j = requests.get(f"{DART}/list.json", params={
            "crtfc_key": key, "corp_cls": "Y", "pblntf_ty": "B", "bgn_de": day, "end_de": day,
            "page_no": page, "page_count": 100}, timeout=30).json()
        if j.get("status") == "013":
            break
        if j.get("status") != "000":
            sys.exit(f"::error::DART 응답 {j.get('status')} {j.get('message')}")
        for it in j.get("list", []):
            nm = re.sub(r"\s+", "", it.get("report_nm", ""))
            if BUYBACK.search(nm) and it.get("stock_code"):
                out.append({"code": it["stock_code"], "corp": it.get("corp_name", ""), "rcept_no": it["rcept_no"],
                            "kind": "신탁계약" if "신탁" in nm else "직접취득", "report": it["report_nm"].strip()})
        if page >= int(j.get("total_page", 1)):
            break
        page += 1
        time.sleep(0.2)
    return out


def quote(code: str):
    """현재가·등락률(네이버) + 20일 평균 거래대금·RSI14(일봉, 오늘 포함)."""
    info = {}
    try:
        j = requests.get(f"https://m.stock.naver.com/api/stock/{code}/basic", headers=UA, timeout=10).json()
        info["price"] = float(str(j.get("closePrice", "")).replace(",", "") or "nan")
        info["chg"] = float(j.get("fluctuationsRatio") or "nan")
    except Exception:
        pass
    try:
        d = daily(code, (datetime.now(KST) - timedelta(days=90)).strftime("%Y%m%d"))
        info["tv20"] = float((d["Close"] * d["Volume"]).iloc[-21:-1].mean())   # 오늘(미완성) 제외
        info["rsi"] = float(rsi(d["Close"]).iloc[-1])
    except Exception:
        pass
    return info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--any-time", action="store_true", help="시간 제한 없이 실행(시험용)")
    a = ap.parse_args()
    now = datetime.now(KST)
    if not a.any_time and (now.weekday() >= 5 or not (7 <= now.hour < 19)):
        print(f"KST {now:%a %H:%M} — 평일 07~19시에만 확인합니다.")
        return
    day = now.strftime("%Y%m%d")
    seen = json.load(open(SEEN, encoding="utf-8")) if os.path.exists(SEEN) else {}
    seen = {k: v for k, v in seen.items() if k >= (now - timedelta(days=7)).strftime("%Y%m%d")}
    done = set(seen.get(day, []))
    fresh = [e for e in todays_buybacks(day) if e["rcept_no"] not in done]
    print(f"KST {now:%H:%M} 오늘 자사주 공시 새로 {len(fresh)}건")
    if not fresh:
        return
    L = [f"⚡ 자사주 공시 알림 · {now:%m/%d %H:%M} 확인", ""]
    for e in fresh:
        q = quote(e["code"])
        px = f"{q['price']:,.0f}원 ({q['chg']:+.1f}%)" if "price" in q and q["price"] == q["price"] else "현재가 조회 실패"
        tv = q.get("tv20")
        liq = "" if tv is None else (f" · 20일 거래대금 {tv / 1e8:,.0f}억" + (" ⚠️ 3억 미만, 모의투자 제외" if tv < BB_LIQ else ""))
        r = f" · RSI {q['rsi']:.0f}" if "rsi" in q else ""
        L.append(f"• {e['corp']} — {e['kind']}")
        L.append(f"  {px}{r}{liq}")
        L.append(f"  https://dart.fss.or.kr/dsaf001/main.do?rcpNo={e['rcept_no']}")
    L += ["", "참고(2015~2026 백테스트): 다음 날 시가 매수 후 20일 평균 +1.7%(유사 종목 대비),",
          "공시 당일 +3~7% 오른 경우 +2.0%. 모의투자는 규칙대로 내일 시가 매수로 기록합니다."]
    text = "\n".join(L)
    print(text)
    if a.dry_run:
        return
    send(text)
    gchat = os.environ.get("GROUP_CHAT_ID", "").strip()
    if gchat:
        os.environ["TELEGRAM_CHAT_ID"] = gchat
        try:
            send(text)
        except SystemExit as ex:
            print("::warning::그룹 전송 실패", ex)
    seen[day] = sorted(done | {e["rcept_no"] for e in fresh})
    with open(SEEN, "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
