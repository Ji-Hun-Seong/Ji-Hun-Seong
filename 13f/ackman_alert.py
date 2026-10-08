"""
13F 신규 공시 감지 → 텔레그램 알림
- 매일 GitHub Actions가 실행. 새 13F가 있으면 '신규/증액/축소/전량매도'를 텔레그램으로 전송
- 마지막으로 알린 공시번호는 state.json에 저장(워크플로가 커밋)
필요한 환경변수(GitHub Secrets): TG_TOKEN, TG_CHAT_ID, SEC_UA
"""
import html, json, os, time
import xml.etree.ElementTree as ET
from pathlib import Path
import requests

# 추적할 매니저 (CIK는 EDGAR에서 확인 후 추가/수정)
MANAGERS = {
    "Pershing Square (Ackman)": "0002026053",   # 2026년 상장 후 Pershing Square Inc.로 제출 (옛 CIK 0001336528),
    "Baron Capital (Ron Baron)": "0001017918",
}
HEADERS = {"User-Agent": os.environ.get("SEC_UA", "Your Name your@email.com")}
STATE = Path(__file__).with_name("state.json")


def get(url):
    time.sleep(0.15)
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r


def filings(cik):
    rec = get(f"https://data.sec.gov/submissions/CIK{cik}.json").json()["filings"]["recent"]
    return [(a, rd, fd) for f, a, rd, fd in
            zip(rec["form"], rec["accessionNumber"], rec["reportDate"], rec["filingDate"])
            if f in ("13F-HR", "13F-HR/A")]


def holdings(cik, acc):
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}"
    items = get(f"{base}/index.json").json()["directory"]["item"]
    xml = next(i["name"] for i in items
               if i["name"].endswith(".xml") and "primary_doc" not in i["name"])
    root = ET.fromstring(get(f"{base}/{xml}").content)
    ns = {"n": root.tag.split("}")[0].strip("{")}
    out = {}
    for it in root.findall("n:infoTable", ns):
        if it.findtext("n:putCall", default="", namespaces=ns):
            continue                                   # 옵션 제외, 현물만
        key = it.findtext("n:cusip", namespaces=ns)
        name = it.findtext("n:nameOfIssuer", namespaces=ns)
        v = int(it.findtext("n:value", namespaces=ns))
        s = int(it.findtext("n:shrsOrPrnAmt/n:sshPrnamt", namespaces=ns))
        o = out.setdefault(key, {"name": name, "value": 0, "shares": 0})
        o["value"] += v; o["shares"] += s
    return out


def diff_message(label, cik, new, old):
    acc, rep, filed = new
    cur, prev = holdings(cik, acc), holdings(cik, old[0])
    total = sum(h["value"] for h in cur.values()) or 1
    rows, exits = [], []
    for k, h in sorted(cur.items(), key=lambda x: -x[1]["value"]):
        w = h["value"] / total * 100
        p = prev.get(k)
        if not p:
            tag = "🆕 신규"
        else:
            chg = (h["shares"] / p["shares"] - 1) * 100 if p["shares"] else 0
            tag = "유지" if abs(chg) < 0.5 else f"{'▲' if chg > 0 else '▼'}{chg:+.0f}%"
        rows.append((w, tag, html.escape(h["name"][:22])))
    for k, p in prev.items():
        if k not in cur:
            exits.append(html.escape(p["name"][:22]))
    top = rows[:15]                                   # 상위 15종목
    others_new = [r for r in rows[15:] if r[1] == "🆕 신규"][:10]
    lines = [f"📊 <b>{html.escape(label)}</b> 13F 신규 공시",
             f"기준일 {rep} · 제출 {filed} · {len(cur)}종목 · ${total/1e9:.1f}B", ""]
    lines += [f"{n} {w:.1f}% {t}" for w, t, n in top]
    if len(rows) > 15:
        lines.append(f"…외 {len(rows) - 15}종목")
    if others_new:
        lines += ["", "<b>기타 신규</b>"] + [f"{n} {w:.1f}%" for w, t, n in others_new]
    if exits:
        lines += ["", f"<b>❌ 전량매도 {len(exits)}종목</b>", ", ".join(exits[:20])]
    lines += ["", f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&amp;CIK={cik}&amp;type=13F"]
    text = "\n".join(lines)
    return text[:4000]


def send(text):
    requests.post(
        f"https://api.telegram.org/bot{os.environ['TG_TOKEN']}/sendMessage",
        json={"chat_id": os.environ["TG_CHAT_ID"], "text": text,
              "parse_mode": "HTML", "disable_web_page_preview": True},
        timeout=30,
    ).raise_for_status()


def main():
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    errors = []
    for label, cik in MANAGERS.items():
      try:
        fl = filings(cik)
        if len(fl) < 2:
            continue
        latest = fl[0]
        test = os.environ.get("TEST") == "1"           # 수동 테스트: 최신 공시를 바로 전송
        if state.get(cik) == latest[0] and not test:
            continue                                   # 이미 알린 공시
        if cik in state or test:                       # 첫 실행은 기록만, 알림 X
            send(diff_message(label, cik, latest, fl[1]))
        state[cik] = latest[0]
      except Exception as e:
        errors.append(f"{label}: {type(e).__name__}: {str(e).replace(os.environ.get('TG_TOKEN','x'),'***')[:250]}")
    for m in errors:
        print(f"::error::{m}")
    STATE.write_text(json.dumps(state, indent=2))


if __name__ == "__main__":
    import sys, traceback
    missing = [k for k in ("TG_TOKEN", "TG_CHAT_ID", "SEC_UA") if not os.environ.get(k)]
    if missing:
        print(f"::error::GitHub Secrets 누락: {', '.join(missing)}")
        sys.exit(1)
    try:
        main()
    except Exception as e:
        traceback.print_exc()
        msg = str(e).replace(os.environ.get("TG_TOKEN", "x"), "***")
        print(f"::error::{type(e).__name__}: {msg[:300]}")
        sys.exit(1)
