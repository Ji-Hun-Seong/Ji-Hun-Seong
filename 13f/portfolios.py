"""
매니저별 최신 13F 전체 포트폴리오 → 텔레그램 (수동 실행 전용)
  python 13f/portfolios.py            # 미리보기: 메시지를 Actions 주석(notice)으로만 출력
  python 13f/portfolios.py --send     # 텔레그램 전송
환경변수: SEC_UA, (전송 시) TG_TOKEN, TG_CHAT_ID
"""
import html, os, re, sys, time
import xml.etree.ElementTree as ET
import requests

HEADERS = {"User-Agent": os.environ.get("SEC_UA", "Your Name your@email.com")}
TOP_N = 25

# (표시 이름, 스타일, CIK 또는 None, CIK가 없을 때 EDGAR 이름 검색어)
MANAGERS = [
    ("빌 애크먼 · Pershing Square", "가치", None, "pershing square"),
    ("프렘 왓사 · Fairfax", "가치", None, "fairfax financial"),
    ("데이비드 테퍼 · Appaloosa", "가치", "0001656456", None),
    ("스탠리 드러켄밀러 · Duquesne", "성장", "0001536411", None),
]

# 제출 법인이 바뀐 경우 직전 분기 비교용 옛 CIK
PREV_CIK = {"빌 애크먼 · Pershing Square": "0001336528"}

NOTES = {
    "프렘 왓사 · Fairfax": "※ 13F는 페어팩스의 미국 상장주식 일부만 보여줌. 진짜 '따라하기'는 페어팩스(FFH) 주식 자체 보유.",
    "데이비드 테퍼 · Appaloosa": "※ 역발상 가치 스타일이지만 현재 보유는 기술주 위주.",
    "빌 애크먼 · Pershing Square": "※ 5년 조건 미달(13F 5년 +17%, 실제 펀드 연 ~8%)이지만 요청에 따라 포함.",
    "스탠리 드러켄밀러 · Duquesne": "※ 종목 수·회전율이 높아 공시 시점엔 이미 바뀌었을 가능성 큼.",
}

WYMER = """🟩 <b>스티브 와이머 · Fidelity Growth Company</b> [성장]
기준 2026-05-31 (반기보고서) · 5년 연 18.5% · 10년 연 23.6%

NVIDIA 15.8%
Apple 7.6%
Alphabet (A+C) 7.6%
Microsoft 5.9%
Amazon 5.3%
Sandisk 3.9%
Ciena 3.8%
Meta 2.8%
Broadcom 2.3%

※ 공모펀드라 13F가 따로 없음. 상위 10종목만 공개 자료 기준(약 59%), 나머지는 소규모 다수.
※ 신규 투자자 가입 제한 펀드 → 보유종목을 참고하는 방식으로 따라하기."""


def get(url):
    time.sleep(0.2)
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r


def find_cik(query):
    page = get("https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=13F-HR"
               f"&owner=include&count=40&company={requests.utils.quote(query)}").text
    ciks = list(dict.fromkeys(re.findall(r"CIK=(\d{10})", page)))
    single = re.search(r'name="CIK"[^>]*value="(\d+)"', page) or re.search(r"CIK=(\d+)&amp;type", page)
    if not ciks and single:
        ciks = [single.group(1).zfill(10)]
    best = None
    for cik in ciks[:15]:
        d = get(f"https://data.sec.gov/submissions/CIK{cik}.json").json()
        rec = d["filings"]["recent"]
        dates = [fd for f, fd in zip(rec["form"], rec["filingDate"]) if f.startswith("13F-HR")]
        print(f"::notice::후보 {query}: {d['name']} CIK {cik} 13F {len(dates)}건, 최근 {max(dates) if dates else '-'}")
        if dates and (best is None or max(dates) > best[1]):
            best = (cik, max(dates), d["name"])
    if not best:
        raise RuntimeError(f"13F 제출자를 못 찾음: {query}")
    print(f"::notice::{query} → {best[2]} CIK {best[0]} (최근 13F {best[1]})")
    return best[0]


def filings(cik):
    rec = get(f"https://data.sec.gov/submissions/CIK{cik}.json").json()["filings"]["recent"]
    seen, out = set(), []
    for f, a, rd, fd in zip(rec["form"], rec["accessionNumber"], rec["reportDate"], rec["filingDate"]):
        if f in ("13F-HR", "13F-HR/A") and rd not in seen:   # 기준일별 최신 제출본(정정 포함)
            seen.add(rd); out.append((a, rd, fd))
    return out


def holdings(cik, acc):
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}"
    items = get(f"{base}/index.json").json()["directory"]["item"]
    xml = next(i["name"] for i in items
               if i["name"].lower().endswith(".xml") and "primary_doc" not in i["name"].lower())
    root = ET.fromstring(get(f"{base}/{xml}").content)
    ns = {"n": root.tag.split("}")[0].strip("{")}
    out = {}
    for it in root.findall("n:infoTable", ns):
        pc = it.findtext("n:putCall", default="", namespaces=ns).strip()
        key = (it.findtext("n:cusip", namespaces=ns), pc)
        name = it.findtext("n:nameOfIssuer", namespaces=ns).strip()
        cls = (it.findtext("n:titleOfClass", default="", namespaces=ns) or "").strip()
        if re.search(r"ETF|MSCI|INDEX|S&P|TRUST|FUND", cls.upper()):
            name = cls
        o = out.setdefault(key, {"name": name, "pc": pc, "value": 0, "shares": 0})
        o["value"] += int(float(it.findtext("n:value", namespaces=ns)))
        o["shares"] += int(float(it.findtext("n:shrsOrPrnAmt/n:sshPrnamt", namespaces=ns)))
    px = sorted(o["value"] / o["shares"] for o in out.values() if o["shares"] and not o["pc"])
    if px and px[len(px) // 2] < 2:          # 천 달러 단위로 신고한 경우 보정
        for o in out.values():
            o["value"] *= 1000
    return out


def message(label, style, cik):
    fl = filings(cik)
    (acc, rep, filed) = fl[0]
    pcik = PREV_CIK.get(label, cik)
    older = [f for f in (filings(pcik) if pcik != cik else fl) if f[1] < rep]
    cur = holdings(cik, acc)
    prev = holdings(pcik, older[0][0]) if older else {}
    total = sum(h["value"] for h in cur.values()) or 1
    rows = []
    for k, h in sorted(cur.items(), key=lambda x: -x[1]["value"]):
        p = prev.get(k)
        if not p:
            tag = "🆕"
        else:
            chg = (h["shares"] / p["shares"] - 1) * 100 if p["shares"] else 0
            tag = "" if abs(chg) < 0.5 else f"{'▲' if chg > 0 else '▼'}{abs(chg):.0f}%"
        name = h["name"].title()[:24] + (f" ({h['pc']})" if h["pc"] else "")
        rows.append(f"{html.escape(name, quote=False)} {h['value'] / total * 100:.1f}% {tag}".rstrip())
    exits = [html.escape(p["name"].title()[:24], quote=False) for k, p in prev.items() if k not in cur]
    icon = "🟦" if style == "가치" else "🟩"
    lines = [f"{icon} <b>{html.escape(label)}</b> [{style}]",
             f"13F 기준일 {rep} (제출 {filed}) · {len(cur)}종목 · ${total / 1e9:.2f}B", ""]
    lines += rows[:TOP_N]
    if len(rows) > TOP_N:
        rest = sum(h["value"] for h in sorted(cur.values(), key=lambda h: -h["value"])[TOP_N:])
        lines.append(f"…외 {len(rows) - TOP_N}종목 (합계 {rest / total * 100:.1f}%)")
    if exits:
        lines += ["", f"❌ 전량매도 {len(exits)}: " + ", ".join(exits[:15]) + (" …" if len(exits) > 15 else "")]
    lines += ["", "🆕 신규 · ▲▼ 직전 분기 대비 주식수 변화 · (Call/Put) 옵션", NOTES.get(label, "")]
    return "\n".join(lines)[:4000]


def send(text):
    r = requests.post(f"https://api.telegram.org/bot{os.environ['TG_TOKEN']}/sendMessage",
                      json={"chat_id": os.environ["TG_CHAT_ID"], "text": text,
                            "parse_mode": "HTML", "disable_web_page_preview": True}, timeout=30)
    if not r.ok:
        raise RuntimeError(f"텔레그램 {r.status_code}: {r.text[:200]}")


def find_chats():
    r = requests.get(f"https://api.telegram.org/bot{os.environ['TG_TOKEN']}/getUpdates", timeout=30).json()
    chats = {}
    for u in r.get("result", []):
        for k in ("message", "my_chat_member", "chat_member", "channel_post"):
            c = (u.get(k) or {}).get("chat")
            if c:
                chats[c["id"]] = (c.get("type"), c.get("title") or c.get("username") or "")
    for cid, (typ, title) in chats.items():
        print(f"::notice::chat {cid} | {typ} | {title}")
    g = requests.get(f"https://api.telegram.org/bot{os.environ['TG_TOKEN']}/getChat",
                     params={"chat_id": os.environ.get("TG_CHAT_ID")}, timeout=30).json()
    print(f"::notice::getChat {os.environ.get('TG_CHAT_ID')}: {str(g)[:400]}")
    if not chats:
        print("::warning::업데이트 없음 — 그룹에서 /start@BilAckman_bot 을 보낸 뒤 다시 실행")


def main():
    if "--find-chat" in sys.argv:
        return find_chats()
    do_send = "--send" in sys.argv
    msgs = []
    for label, style, cik, query in MANAGERS:
        try:
            msgs.append(message(label, style, cik or find_cik(query)))
        except Exception as e:
            print(f"::error::{label}: {type(e).__name__}: {str(e)[:300]}")
    msgs.append(WYMER)
    intro = ("📂 <b>빌 애크먼 + 나스닥100을 5년간 이긴 매니저 4인 · 포트폴리오</b>\n"
             "기준: 최근 5년 수익률이 나스닥100(연 16.6%)보다 높을 것\n"
             "✅ 프렘 왓사(페어팩스 주가 +310%) · 데이비드 테퍼(13F +183%) · "
             "스탠리 드러켄밀러(13F +146%) · 스티브 와이머(연 17.7%)\n"
             "⚠️ 애크먼은 조건 미달(13F 5년 +17%)이지만 포함\n"
             "※ 13F = SEC 분기 공시(분기말 기준, 최대 45일 지연). 비중은 신고 금액 대비. 투자 자문 아님.")
    msgs[0] = intro + "\n\n" + msgs[0]
    for i, m in enumerate(msgs, 1):
        if do_send:
            try:
                send(m)
                print(f"::notice::전송 {i}/{len(msgs)} 완료")
            except Exception as e:
                print(f"::error::전송 {i}/{len(msgs)} 실패: {str(e).replace(os.environ['TG_TOKEN'], '***')[:300]}")
                sys.exit(1)
            time.sleep(1)
        else:
            print("::notice::" + m.replace("%", "%25").replace("\n", "%0A"))
    if len(msgs) < len(MANAGERS) + 1:
        sys.exit(1)


if __name__ == "__main__":
    main()
