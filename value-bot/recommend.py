"""
recommend.py — 내 매매일지 DNA로 '내가 관심 가질 가치주 20선'을 뽑는 봇

실행:
    python recommend.py                      # journals/ + universe.csv 로 추천, report.html 생성
    python recommend.py --top 20 --telegram  # 텔레그램으로도 전송(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)
    python recommend.py --include-kosdaq     # 코스닥 후보도 허용(기본: 코스피만)
    python recommend.py --include-holdings   # 이미 보유 중인 종목도 순위에 포함

점수 = 밸류에이션 25 + 주주환원 25 + 현금흐름·재무 25 + 내 성향 적합도 25 − 리스크 감점
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import date

from value_dna import DNA, TAXONOMY, build_dna, kosdaq_names, load_journals

HERE = os.path.dirname(os.path.abspath(__file__))

AXIS_WEIGHTS = {"value": 0.25, "payout": 0.25, "cash": 0.25, "fit": 0.25}

# 리스크 플래그 → (감점, 사람이 읽을 설명)
PENALTIES = {
    "governance":     (12, "지배구조 리스크(소수주주 이익과 충돌한 이력)"),
    "capital_funded": (6,  "배당 재원이 이익이 아니라 자본준비금(감액배당)·배당성향 과다"),
    "div_cut":        (6,  "최근 배당 삭감"),
    "loss":           (5,  "최근 순손실(PER 음수)"),
    "dilution":       (4,  "주식교환·신주발행으로 희석"),
    "split":          (3,  "최근 인적분할로 과거 수치 비교가 어려움"),
    "earnings_drop":  (4,  "최근 분기 이익 급감"),
    "single_product": (3,  "단일 제품 의존도"),
    "high_debt":      (0,  "순차입이 큼(현금흐름 점수에 반영)"),
    "activist":       (0,  "행동주의 펀드 관여(촉매 가능성)"),
    "insurer":        (0,  "보험사: 현금흐름·순현금 지표는 중립 처리"),
    "fin_segment":    (0,  "금융부문 포함 연결이라 현금흐름 지표는 중립 처리"),
}

MAX_VALUE_PBR = 1.5     # 이보다 비싸면 '가치주'가 아니라고 보고 제외


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def num(s):
    s = (s or "").strip()
    return float(s) if s else None


@dataclass
class Candidate:
    row: dict
    scores: dict = field(default_factory=dict)
    penalty: float = 0
    total: float = 0
    reasons: list = field(default_factory=list)
    risks: list = field(default_factory=list)
    excluded: str = ""

    @property
    def name(self):
        return self.row["name"]

    @property
    def flags(self):
        return [f for f in (self.row.get("flags") or "").split(";") if f]


def load_universe(path) -> list[Candidate]:
    with open(path, encoding="utf-8-sig") as f:
        return [Candidate(r) for r in csv.DictReader(f)]


# ---------------------------------------------------------------------------
# 축별 점수 (0~100). 데이터가 없는 항목은 중립(50)으로 본다.
# ---------------------------------------------------------------------------
def _avg(parts):
    # 데이터가 없는 항목은 중립 50점으로 채운다(없는 정보로 득점하지 않도록).
    parts = [(50.0 if s is None else s, w) for s, w in parts]
    return sum(s * w for s, w in parts) / sum(w for _, w in parts)


def score_value(r):
    pbr, per = num(r["pbr"]), num(r["per"])
    s_pbr = None if pbr is None else 100 * clamp((1.2 - pbr) / 1.1)
    if per is None:
        s_per = None
    elif per <= 0:
        s_per = 15.0
    else:
        s_per = 100 * clamp((15 - per) / 12)
    return _avg([(s_pbr, 0.65), (s_per, 0.35)])


def dps_trend(r):
    d = [num(r["dps23"]), num(r["dps24"]), num(r["dps25"])]
    known = [x for x in d if x]
    if len(known) < 2:
        return None, None, False
    first, last = known[0], known[-1]
    years = 2 if (d[0] and d[2]) else 1
    cagr = (last / first) ** (1 / years) - 1
    cut = any(b < a for a, b in zip(known, known[1:]))
    return cagr, last, cut


def score_payout(r):
    y = num(r["yield_pct"])
    s_y = None if y is None else 100 * clamp(y / 6)
    cagr, _, cut = dps_trend(r)
    if cagr is None:
        s_t = None
    else:
        s_t = clamp(0.5 + cagr * 2.5) * 100 - (30 if cut else 0)
        s_t = max(s_t, 0)
    bb = int(num(r["buyback"]) or 0)
    s_b = {0: 0, 1: 50, 2: 100}[bb]
    return _avg([(s_y, 0.40), (s_t, 0.35), (s_b, 0.25)])


def score_cash(r):
    ocf = [num(r["ocf23"]), num(r["ocf24"]), num(r["ocf25"])]
    capex, nc, mcap = num(r["capex25"]), num(r["net_cash"]), num(r["mcap"])
    known = [x for x in ocf if x is not None]
    s_cons = 100 * sum(1 for x in known if x > 0) / len(known) if known else None
    s_fcf = None
    if ocf[2] is not None and capex is not None and mcap:
        fcf_y = (ocf[2] - capex) / mcap
        s_fcf = 100 * clamp((fcf_y + 0.02) / 0.17)      # -2% → 0점, 15% → 100점
    s_nc = None
    if nc is not None and mcap:
        s_nc = 100 * clamp((nc / mcap + 0.5) / 1.0)      # 순차입 50% → 0점, 순현금 50% → 100점
    return _avg([(s_cons, 0.30), (s_fcf, 0.35), (s_nc, 0.35)])


def score_fit(r, dna: DNA, include_kosdaq: bool):
    kind = dna.kind_aff.get(r["kind"], 0)
    sector = dna.sector_aff.get(r["sector"], 0)
    if r["sector"] == "지주(복합)":       # 복합지주는 업종 대신 지주 선호로 대체
        sector = dna.kind_aff.get("holdco", 0) * 0.8
    g = r["group"]
    traded_groups = {TAXONOMY[n]["group"] for n in dna.traded if n in TAXONOMY}
    group = 0.0
    if g in traded_groups:
        pnl = dna.tag_pnl.get(("group", g), 0)
        group = 1.0 if pnl > 0 else 0.5
        group = max(group, dna.group_aff.get(g, 0))
    s = 100 * (0.40 * kind + 0.40 * sector + 0.20 * group)
    if r["market"] == "KOSDAQ" and include_kosdaq:
        s *= 0.6
    return s


# ---------------------------------------------------------------------------
# 사람이 읽는 추천 사유
# ---------------------------------------------------------------------------
KIND_KO = {"holdco": "지주사", "pref": "우선주", "operating": "사업회사"}


def explain(c: Candidate, dna: DNA):
    r = c.row
    why = []
    g = r["group"]
    if c.name in dna.traded:
        if c.name in dna.book:
            why.append(f"직접 매매해 본 종목(실현손익 {dna.book[c.name].pnl / 1e4:+,.0f}만 원) — 재진입 후보")
        else:
            why.append("직접 매매해 본 종목 — 재진입 후보")
    group_traded = [n for n in dna.traded
                    if TAXONOMY.get(n, {}).get("group") == g and n != c.name]
    if group_traded:
        why.append(f"이미 매매해 본 {g} 계열({', '.join(group_traded[:3])})")
    if r["kind"] == "holdco":
        why.append("지주 할인 종목(KPX홀딩스·세아베스틸지주·DL과 같은 유형)")
    if r["kind"] == "pref":
        why.append("우선주 할인(현대차3우B·코오롱인더우에서 수익 낸 유형)")
    if r["sector"] in ("자동차·부품",) and r["kind"] != "pref":
        why.append("가장 많이 번 업종인 자동차·부품")
    pbr = num(r["pbr"])
    if pbr is not None and pbr <= 0.35:
        why.append(f"PBR {pbr:.2f}배")
    cagr, last, cut = dps_trend(r)
    if cagr is not None and cagr > 0.08 and not cut:
        why.append(f"DPS 연 {cagr:.0%} 증가")
    if int(num(r["buyback"]) or 0) == 2:
        why.append("자사주 소각")
    nc, mcap = num(r["net_cash"]), num(r["mcap"])
    if nc is not None and mcap and nc / mcap > 0.2:
        why.append(f"순현금이 시총의 {nc / mcap:.0%}")
    ocf = [num(r[k]) for k in ("ocf23", "ocf24", "ocf25")]
    if all(x is not None and x > 0 for x in ocf) and num(r["capex25"]) is not None and mcap:
        fcf_y = (ocf[2] - num(r["capex25"])) / mcap
        if fcf_y > 0.08:
            why.append(f"FCF 수익률 {fcf_y:.0%}")
    c.reasons = why
    c.risks = [PENALTIES[f][1] for f in c.flags if f in PENALTIES]


def rank(dna: DNA, universe: list[Candidate], include_kosdaq=False, include_holdings=False):
    held = set(dna.holdings)
    for c in universe:
        r = c.row
        pbr = num(r["pbr"])
        if r["market"] != "KOSPI" and not include_kosdaq:
            c.excluded = "코스닥(기본 설정은 코스피만)"
        elif pbr is not None and pbr > MAX_VALUE_PBR:
            c.excluded = f"PBR {pbr:.1f}배로 가치주 범위 밖"
        elif c.name in held and not include_holdings:
            c.excluded = "이미 보유 중"
        c.scores = {
            "value": score_value(r),
            "payout": score_payout(r),
            "cash": score_cash(r),
            "fit": score_fit(r, dna, include_kosdaq),
        }
        c.penalty = sum(PENALTIES.get(f, (0, ""))[0] for f in c.flags)
        c.total = sum(c.scores[k] * w for k, w in AXIS_WEIGHTS.items()) - c.penalty
        explain(c, dna)
    picked = sorted([c for c in universe if not c.excluded], key=lambda c: -c.total)
    return picked, [c for c in universe if c.excluded]


# ---------------------------------------------------------------------------
# 출력
# ---------------------------------------------------------------------------
def console(picked, top):
    print(f"\n{'순위':>3}  {'종목':<12}{'총점':>6}  밸류 환원 현금 적합  감점")
    for i, c in enumerate(picked[:top], 1):
        s = c.scores
        print(f"{i:>3}  {c.name:<12}{c.total:6.1f}  {s['value']:4.0f} {s['payout']:4.0f} "
              f"{s['cash']:4.0f} {s['fit']:4.0f}  -{c.penalty:.0f}")


def _eok(v):
    """억원 숫자를 '2.33조' / '1,421억' 형태로."""
    if v is None:
        return "-"
    return f"{v / 10000:+.2f}조".replace("+", "") if abs(v) >= 10000 else f"{v:,.0f}억"


def fin_block(c):
    """종목 하나의 재무 요약(텔레그램용 여러 줄)."""
    r = c.row
    pbr, per, y, mcap = num(r["pbr"]), num(r["per"]), num(r["yield_pct"]), num(r["mcap"])
    head = []
    if mcap:
        head.append(f"시총 {_eok(mcap)}")
    if per is not None:
        head.append(f"PER {per:.1f}" if per > 0 else "PER 적자")
    if pbr is not None:
        head.append(f"PBR {pbr:.2f}")
    if y is not None:
        head.append(f"배당 {y:.1f}%")
    out = ["   " + " · ".join(head)] if head else []
    dps = [num(r[k]) for k in ("dps23", "dps24", "dps25")]
    if any(dps):
        out.append("   DPS(23→25) " + " → ".join("-" if d is None else f"{d:,.0f}" for d in dps) + "원")
    flags = c.flags
    if "insurer" in flags or "fin_segment" in flags:
        out.append("   현금흐름: " + ("보험사라 생략" if "insurer" in flags else "금융부문 포함 연결이라 생략"))
        return out
    ocf = [num(r[k]) for k in ("ocf23", "ocf24", "ocf25")]
    if any(x is not None for x in ocf):
        out.append("   영업CF(23·24·25) " + " / ".join(_eok(x) for x in ocf))
    capex = num(r["capex25"])
    if ocf[2] is not None and capex is not None:
        fcf = ocf[2] - capex
        fy = f" (시총 대비 {fcf / mcap:.1%})" if mcap else ""
        out.append(f"   CAPEX {_eok(capex)} · FCF {_eok(fcf)}{fy}")
    nc = num(r["net_cash"])
    if nc is not None:
        lab = "순현금" if nc >= 0 else "순차입"
        ratio = f" (시총의 {abs(nc) / mcap:.0%})" if mcap else ""
        out.append(f"   {lab} {_eok(abs(nc))}{ratio}")
    return out


def telegram_messages(picked, top, dna, asof=""):
    """1통: 20선 요약 / 이후: 종목별 근거·리스크·재무 (4,000자 단위로 분할)."""
    summary = [f"📈 가치주 DNA {top}선 — {date.today():%Y-%m-%d}",
               "매매일지 성향 × 밸류·환원·현금흐름 점수 (코스피, 보유 종목 제외)", ""]
    for i, c in enumerate(picked[:top], 1):
        summary.append(f"{i:>2}. {c.name} {c.total:.0f}점")
    summary += ["", "종목별 근거·재무는 다음 메시지에 이어집니다.",
                f"데이터 기준 {asof or '-'} · 단위 억원 · 매수 전 DART 원문 확인"]
    blocks = []
    for i, c in enumerate(picked[:top], 1):
        s = c.scores
        b = [f"{i}. {c.name} ({c.row['ticker']}) {c.total:.0f}점",
             f"   밸류 {s['value']:.0f} · 환원 {s['payout']:.0f} · 현금 {s['cash']:.0f} · 적합 {s['fit']:.0f}"]
        why = [w for w in c.reasons if "재진입" not in w][:3] or [c.row.get("note", "")]
        b.append(f"   ✓ {', '.join(why)}")
        risk = [x for x in c.risks if "중립" not in x and "반영" not in x and "촉매" not in x]
        if risk:
            b.append(f"   ⚠ {risk[0]}")
        b += fin_block(c)
        if c.row.get("note"):
            b.append(f"   ※ {c.row['note']}")
        blocks.append("\n".join(b))
    msgs, cur = ["\n".join(summary)], ""
    for b in blocks:
        if len(cur) + len(b) + 2 > 4000:
            msgs.append(cur)
            cur = ""
        cur = f"{cur}\n\n{b}" if cur else b
    if cur:
        msgs.append(cur)
    return msgs


def telegram_text(picked, top, dna, asof=""):
    return "\n\n".join(telegram_messages(picked, top, dna, asof))


def _tg_token():
    import re
    tok = os.environ.get("TELEGRAM_TOKEN") or os.environ.get("TG_TOKEN") or ""
    m = re.search(r"\d{6,}:[A-Za-z0-9_-]{30,}", tok)       # 공백·줄바꿈·'bot' 접두어 정리
    return m.group(0) if m else tok.strip()


def send_telegram(messages):
    import time
    import requests
    if isinstance(messages, str):
        messages = [messages]
    tok = _tg_token()
    chat = (os.environ.get("TELEGRAM_CHAT_ID") or os.environ.get("TG_CHAT_ID") or "").strip()
    if not (tok and chat):
        sys.exit("::error::TG_TOKEN / TG_CHAT_ID (또는 TELEGRAM_TOKEN / TELEGRAM_CHAT_ID) 가 없습니다.")
    for i, text in enumerate(messages, 1):
        for _ in range(2):
            r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                              json={"chat_id": chat, "text": text, "disable_web_page_preview": True}, timeout=20)
            new_id = (r.json().get("parameters") or {}).get("migrate_to_chat_id") if r.status_code == 400 else None
            if not new_id:
                break
            # 일반 그룹이 슈퍼그룹으로 바뀌면 chat ID가 바뀐다 → 새 ID로 재시도하고 그룹에 알림
            chat = str(new_id)
            print("::warning::그룹 chat ID가 바뀌었습니다. VALUE_TG_CHAT_ID를 그룹 안내 메시지의 새 값으로 바꿔 주세요.")
            requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                          json={"chat_id": chat, "text": f"ℹ️ 이 그룹의 chat ID가 {chat} 로 바뀌었습니다. GitHub 시크릿 VALUE_TG_CHAT_ID를 이 값으로 바꿔 주세요."},
                          timeout=20)
        if r.status_code != 200:
            hint = " — 토큰이 잘못됐습니다. BotFather의 토큰(숫자:영문 형태)만 VALUE_TG_TOKEN에 다시 넣어 주세요." if r.status_code in (401, 404) else ""
            if r.status_code in (400, 403) and "chat" in r.text:
                hint = " — 봇이 그 대화방에 없거나 chat ID가 틀렸습니다. 봇을 그룹에 초대했는지, VALUE_TG_CHAT_ID 값을 확인해 주세요."
            sys.exit(f"::error::텔레그램 전송 실패({i}/{len(messages)}): {r.status_code} {r.text.replace(tok, '***')[:200]}{hint}")
        time.sleep(1)
    print(f"텔레그램 전송 완료: {len(messages)}통")


def find_chats():
    """봇이 들어가 있는 그룹을 찾아, 각 그룹 안에 그 그룹의 chat ID를 알려 준다(로그에는 ID를 남기지 않음)."""
    import requests
    tok = _tg_token()
    if not tok:
        sys.exit("::error::VALUE_TG_TOKEN 이 없습니다.")
    ups = requests.get(f"https://api.telegram.org/bot{tok}/getUpdates", timeout=20).json().get("result", [])
    chats = {}
    for u in ups:
        for key in ("message", "my_chat_member", "chat_member", "edited_message", "channel_post"):
            ch = (u.get(key) or {}).get("chat")
            if ch and ch.get("type") in ("group", "supergroup"):
                chats[ch["id"]] = ch.get("title", "")
    if not chats:
        sys.exit("::error::봇이 들어간 그룹을 찾지 못했습니다. 그룹에 봇을 초대한 뒤 그룹에서 /start@KoreaValueStock_Bot 을 보내고 24시간 안에 다시 실행해 주세요.")
    for cid, title in chats.items():
        requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", json={
            "chat_id": cid,
            "text": (f"👋 가치주 DNA 봇이 이 그룹({title})에 연결됐습니다.\n\n"
                     f"이 그룹의 chat ID: {cid}\n\n"
                     "GitHub 저장소 Settings → Secrets → Actions 에서 VALUE_TG_CHAT_ID 이름으로 위 숫자(마이너스 포함)를 등록하면 "
                     "매월 1일 20선이 이 그룹으로 옵니다.")}, timeout=20)
    print(f"그룹 {len(chats)}곳에 chat ID 안내를 보냈습니다.")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--journals", default=os.path.join(HERE, "journals"))
    ap.add_argument("--universe", default=os.path.join(HERE, "universe.csv"))
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--include-kosdaq", action="store_true")
    ap.add_argument("--include-holdings", action="store_true")
    ap.add_argument("--html", default=os.path.join(HERE, "report.html"))
    ap.add_argument("--json", default=os.path.join(HERE, "picks.json"))
    ap.add_argument("--telegram", action="store_true")
    ap.add_argument("--profile", help="매매일지 대신 금액 없는 성향 프로필(profile.json) 사용")
    ap.add_argument("--export-profile", help="성향 프로필을 이 경로로 저장")
    ap.add_argument("--no-html", action="store_true")
    ap.add_argument("--find-chats", action="store_true", help="봇이 들어간 그룹에 chat ID 안내 보내기")
    a = ap.parse_args(argv)
    if a.find_chats:
        return find_chats()

    if a.profile:
        from value_dna import load_profile
        dna = load_profile(a.profile)
        a.no_html = True                     # 리포트의 매매 통계는 원본 일지가 있어야 만든다
    else:
        dna = build_dna(load_journals(a.journals))
    if a.export_profile:
        from value_dna import export_profile
        export_profile(dna, a.export_profile)
        print("프로필 저장:", a.export_profile)
    if dna.unknown:
        print("⚠ value_dna.TAXONOMY 에 없는 종목(분류 후 다시 실행):", dna.unknown)
    picked, excluded = rank(dna, load_universe(a.universe), a.include_kosdaq, a.include_holdings)
    console(picked, a.top)

    if not a.no_html:
        from report import render
        open(a.html, "w", encoding="utf-8").write(render(dna, picked[:a.top], excluded, a))
    json.dump([{"rank": i, "name": c.name, "ticker": c.row["ticker"], "total": round(c.total, 1),
                **{k: round(v, 1) for k, v in c.scores.items()}, "reasons": c.reasons, "risks": c.risks}
               for i, c in enumerate(picked[:a.top], 1)],
              open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(("" if a.no_html else f"\n리포트: {a.html}") + f"\nJSON: {a.json}")
    if a.telegram:
        f = os.path.join(os.path.dirname(os.path.abspath(a.universe)), "DATA_ASOF")
        asof = open(f).read().strip() if os.path.exists(f) else ""
        send_telegram(telegram_messages(picked, a.top, dna, asof))


if __name__ == "__main__":
    main()
