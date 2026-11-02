"""펀드회계 백과 공부봇 — lessons_*.md로 GitHub 포스팅과 텔레그램 메시지를 만든다.

  python fund-study/study_bot.py build              # posts/dayNN.md + README.md(목차) 생성
  python fund-study/study_bot.py send               # 다음 차례 Day 전송 (오늘 이미 보냈으면 건너뜀)
  python fund-study/study_bot.py send --force       # 오늘 보냈어도 다음 Day 전송
  python fund-study/study_bot.py send --day 5       # 특정 Day 전송
  python fund-study/study_bot.py preview --day 1    # 미리보기(전송 안 함)

환경변수: TELEGRAM_TOKEN, TELEGRAM_CHAT_ID (개인 채팅만 — 그룹 ID는 거부)
"""
from __future__ import annotations

import datetime as dt
import glob
import html
import json
import os
import re
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
POSTS = os.path.join(HERE, "posts")
PROGRESS = os.path.join(HERE, "progress.json")
REPO_URL = "https://github.com/Ji-Hun-Seong/Ji-Hun-Seong/blob/main/fund-study"
KST = dt.timezone(dt.timedelta(hours=9))
BOOK = "펀드회계 백과"


# ── 파싱: Day → 항목(### 제목) → 블록(문단/목록/분개/mermaid) ─────────────
def load_days() -> list[dict]:
    days, cur, item, fence, buf = [], None, None, None, []
    lines = []
    for f in sorted(glob.glob(os.path.join(HERE, "lessons_*.md"))):
        lines += open(f, encoding="utf-8").read().splitlines()

    def target():
        return item["blocks"] if item else cur["pre"]

    for line in lines:
        if fence:                                   # 코드 블록 안
            if line.strip() == "```":
                target().append({"type": fence, "text": "\n".join(buf)})
                fence, buf = None, []
            else:
                buf.append(line)
            continue
        if m := re.match(r"^## Day (\d+) · (.+)$", line):
            cur = {"n": int(m.group(1)), "title": m.group(2).strip(), "intro": "", "pre": [], "items": []}
            item = None
            days.append(cur)
            continue
        if cur is None:
            continue
        if m := re.match(r"^```(\S+)", line):
            fence = "mermaid" if m.group(1) == "mermaid" else "journal"
            continue
        if line.startswith("### "):
            item = {"term": line[4:].strip(), "blocks": []}
            cur["items"].append(item)
        elif line.startswith("> ") and item is None:
            cur["intro"] = line[2:].strip()
        elif line.startswith("- "):
            target().append({"type": "bullet", "text": line[2:].strip()})
        elif line.strip():
            target().append({"type": "para", "text": line.strip()})
    return days


def post_url(n: int) -> str:
    return f"{REPO_URL}/posts/day{n:02d}.md"


# ── GitHub 포스팅 ───────────────────────────────────
def md_blocks(blocks) -> list[str]:
    out, prev = [], None
    for b in blocks:
        if b["type"] == "bullet":
            if prev != "bullet":
                out.append("")
            out.append(f"- {b['text']}")
        elif b["type"] == "para":
            out += ["", b["text"]]
        elif b["type"] == "journal":
            out += ["", "```text", b["text"], "```"]
        elif b["type"] == "mermaid":
            out += ["", "```mermaid", b["text"], "```"]
        prev = b["type"]
    return out


def build():
    days = load_days()
    os.makedirs(POSTS, exist_ok=True)
    total = len(days)
    for i, d in enumerate(days):
        L = [f"# Day {d['n']} · {d['title']}", "", f"> {d['intro']}", "",
             f"📘 {BOOK} {d['n']}/{total}일차 · 항목 {len(d['items'])}개 · [전체 목차](../README.md)"]
        L += md_blocks(d["pre"])
        L += ["", "**오늘의 항목**: " + " · ".join(it["term"] for it in d["items"]), "", "---"]
        for k, it in enumerate(d["items"], 1):
            L += ["", f"## {k}. {it['term']}"] + md_blocks(it["blocks"])
        nav = []
        if i > 0:
            p = days[i - 1]; nav.append(f"[← Day {p['n']} {p['title']}](day{p['n']:02d}.md)")
        nav.append("[목차](../README.md)")
        if i < total - 1:
            q = days[i + 1]; nav.append(f"[Day {q['n']} {q['title']} →](day{q['n']:02d}.md)")
        L += ["", "---", "", "> 분개 예시의 숫자는 이해를 돕기 위한 가정입니다. 계정과목 명칭·세부 처리는 사무관리회사·운용사 기준과 최신 법령을 확인하세요.",
              "", " · ".join(nav), ""]
        open(os.path.join(POSTS, f"day{d['n']:02d}.md"), "w", encoding="utf-8").write("\n".join(L))

    n_items = sum(len(d["items"]) for d in days)
    R = [f"# 📘 {BOOK} — 펀드회계 실무자를 위한 자산별 회계처리", "",
         "운용이 아니라 **회계처리와 업무 프로세스** 관점에서 주식·채권·단기자금·파생·외화·부동산·대체자산을 정리한 백과입니다.",
         "매일 저녁 텔레그램으로 하루치가 도착하고, 같은 내용이 아래 포스팅으로 정리됩니다.", "",
         f"총 **{total}일 · 항목 {n_items}개** — 항목마다 개념 → 프로세스 → 분개 예시 → 평가·기준가 영향 → 실무 체크포인트 순서", "",
         "| Day | 주제 | 항목 |", "|:-:|---|:-:|"]
    for d in days:
        R.append(f"| {d['n']} | [{d['title']}](posts/day{d['n']:02d}.md) | {len(d['items'])} |")
    R += ["", "## 구성", "", "```mermaid", "flowchart LR",
          "  A[펀드 구조·기준가<br/>Day 1-2] --> B[주식<br/>Day 3-8]",
          "  B --> C[채권·단기자금·MMF<br/>Day 9-12]", "  C --> D[설정환매·보수<br/>Day 13-14]",
          "  D --> E[파생·외화<br/>Day 15-16]", "  E --> F[부동산·대체<br/>Day 17-18]",
          "  F --> G[결산·세무·검증<br/>Day 19-20]", "```", "",
          "## 주의", "",
          "- 분개 예시 숫자는 가정이며, 계정과목·처리 방식은 회사마다 다를 수 있습니다.",
          "- 세율·결제주기·평가 규정 등은 바뀔 수 있으니 실무 적용 전 최신 법령·사내 기준을 확인하세요.", "",
          "## 파일", "",
          "- `lessons_1.md`, `lessons_2.md` — 원본 (고치면 포스팅·텔레그램이 같이 바뀜)",
          "- `posts/` — Day별 포스팅 (`python fund-study/study_bot.py build`)",
          "- 발송: `.github/workflows/fund-study.yml` (매일 저녁 6시대, 개인 채팅 전용)", ""]
    open(os.path.join(HERE, "README.md"), "w", encoding="utf-8").write("\n".join(R))
    print(f"포스팅 {total}개 · 항목 {n_items}개 + README 생성")


# ── 텔레그램 ────────────────────────────────────────
def tg_blocks(blocks) -> str:
    out = []
    for b in blocks:
        t = html.escape(b["text"], quote=False)
        if b["type"] == "para":
            out.append(t)
        elif b["type"] == "bullet":
            out.append("• " + t)
        elif b["type"] == "journal":
            out.append(f"<pre>{t}</pre>")
        elif b["type"] == "mermaid":
            out.append("🗺️ <i>(흐름도는 포스팅에서 보기)</i>")
    return "\n".join(out)


def messages(d: dict, total: int) -> list[str]:
    head = (f"📘 <b>{BOOK} Day {d['n']}/{total} · {html.escape(d['title'], quote=False)}</b>\n"
            f"{html.escape(d['intro'], quote=False)}\n\n"
            f"오늘 항목 {len(d['items'])}개 · <a href=\"{post_url(d['n'])}\">도식 포함 포스팅 보기</a>")
    pre = tg_blocks(d["pre"])
    if pre.strip():
        head += "\n\n" + pre
    blocks = [f"<b>{k}. {html.escape(it['term'], quote=False)}</b>\n{tg_blocks(it['blocks'])}"
              for k, it in enumerate(d["items"], 1)]
    msgs, cur = [head], ""
    for b in blocks:
        if cur and len(cur) + len(b) + 2 > 3800:
            msgs.append(cur); cur = ""
        cur += ("\n\n" if cur else "") + b
    if cur:
        msgs.append(cur)
    msgs[-1] += "\n\n<i>※ 분개 숫자는 가정 · 사내 기준과 최신 법령을 함께 확인하세요.</i>"
    return msgs


def tg(method: str, **kw):
    tok = (os.environ.get("TELEGRAM_TOKEN") or "").strip()
    chat = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    if not tok or not chat:
        sys.exit("::error::TELEGRAM_TOKEN / TELEGRAM_CHAT_ID 가 없습니다")
    if chat.startswith("-"):   # 그룹·채널 ID는 음수 — 개인 채팅에만 보낸다
        sys.exit("::error::그룹방으로는 보내지 않습니다 (개인 채팅 ID만 허용)")
    for i in range(3):
        r = requests.post(f"https://api.telegram.org/bot{tok}/{method}", data={"chat_id": chat, **kw}, timeout=30)
        if r.ok:
            return r.json()
        print("텔레그램 실패", r.status_code, r.text[:300])
        time.sleep(3)
    raise RuntimeError(f"텔레그램 {method} 실패")


def send_day(d: dict, total: int, dry=False):
    msgs = messages(d, total)
    if dry:
        for i, m in enumerate(msgs):
            print(f"\n----- 메시지 {i + 1} ({len(m)}자)\n{m}")
        return
    for m in msgs:
        tg("sendMessage", text=m, parse_mode="HTML", disable_web_page_preview="true")
        time.sleep(1)


def load_progress():
    try:
        return json.load(open(PROGRESS))
    except Exception:
        return {"next_day": 1, "round": 1, "last_sent": None, "history": []}


def cmd_send(args):
    days = load_days()
    total = len(days)
    prog = load_progress()
    today = dt.datetime.now(KST).date().isoformat()
    if "--day" in args:
        n = int(args[args.index("--day") + 1])
    else:
        if prog.get("last_sent") == today and "--force" not in args:
            print(f"오늘({today}) 이미 보냄 — 건너뜀"); return
        n = prog.get("next_day", 1)
    if n > total:
        n = 1
        prog["round"] = prog.get("round", 1) + 1
    d = next(x for x in days if x["n"] == n)
    if prog.get("round", 1) > 1:
        d = {**d, "title": f"{d['title']} (복습 {prog['round']}회차)"}
    send_day(d, total)
    prog.update(next_day=n + 1, last_sent=today)
    prog.setdefault("history", []).append({"date": today, "day": n})
    prog["history"] = prog["history"][-60:]
    json.dump(prog, open(PROGRESS, "w"), ensure_ascii=False, indent=1)
    print(f"텔레그램 전송 완료: Day {n}")


if __name__ == "__main__":
    a = sys.argv[1:] or ["build"]
    if a[0] == "build":
        build()
    elif a[0] == "send":
        cmd_send(a[1:])
    elif a[0] == "preview":
        days = load_days()
        n = int(a[a.index("--day") + 1]) if "--day" in a else 1
        send_day(next(x for x in days if x["n"] == n), len(days), dry=True)
