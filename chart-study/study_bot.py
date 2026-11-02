"""차트 공부봇 — lessons.md 하나로 GitHub 포스팅과 텔레그램 메시지를 만든다.

  python chart-study/study_bot.py build              # posts/dayNN.md + README.md(목차) 생성
  python chart-study/study_bot.py send               # 다음 차례 Day를 텔레그램으로 (오늘 이미 보냈으면 건너뜀)
  python chart-study/study_bot.py send --force       # 오늘 보냈어도 다음 Day 전송
  python chart-study/study_bot.py send --day 5       # 특정 Day 전송 (진도는 그 다음으로)
  python chart-study/study_bot.py preview --day 1    # 보낼 메시지 미리보기(전송 안 함)

환경변수: TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
LESSONS = os.path.join(HERE, "lessons.md")
POSTS = os.path.join(HERE, "posts")
PROGRESS = os.path.join(HERE, "progress.json")
REPO_URL = "https://github.com/Ji-Hun-Seong/Ji-Hun-Seong/blob/main/chart-study"
KST = dt.timezone(dt.timedelta(hours=9))


# ── 파싱 ────────────────────────────────────────────
def load_days() -> list[dict]:
    days, cur = [], None
    for line in open(LESSONS, encoding="utf-8"):
        line = line.rstrip("\n")
        m = re.match(r"^## Day (\d+) · (.+)$", line)
        if m:
            cur = {"n": int(m.group(1)), "title": m.group(2).strip(), "intro": "", "images": [], "items": []}
            days.append(cur)
            continue
        if cur is None:
            continue
        if line.startswith("> "):
            cur["intro"] = line[2:].strip()
        elif m := re.match(r"^!\[(.*?)\]\((.+?)\)", line):
            cur["images"].append({"alt": m.group(1), "path": m.group(2)})
        elif m := re.match(r"^- \*\*(.+?)\*\*: (.+)$", line):
            cur["items"].append({"term": m.group(1).strip(), "desc": m.group(2).strip()})
    return days


def post_url(n: int) -> str:
    return f"{REPO_URL}/posts/day{n:02d}.md"


# ── GitHub 포스팅 ───────────────────────────────────
def build():
    days = load_days()
    os.makedirs(POSTS, exist_ok=True)
    total = len(days)
    for i, d in enumerate(days):
        L = [f"# Day {d['n']} · {d['title']}", "",
             f"> {d['intro']}", "",
             f"📚 차트 공부 {d['n']}/{total}일차 · 개념 {len(d['items'])}개 · [전체 목차](../README.md)", ""]
        for im in d["images"]:
            L += [f"![{im['alt']}](../{im['path']})", f"<sub>그림: {im['alt']} (개념 설명용 가상 데이터)</sub>", ""]
        L += ["---", ""]
        for k, it in enumerate(d["items"], 1):
            L += [f"### {k}. {it['term']}", "", it["desc"], ""]
        L += ["---", "", "### ✍️ 오늘의 연습", "",
              "관심 종목 하나를 골라 오늘 배운 개념을 실제 차트에서 찾아보세요. "
              "찾은 자리를 캡처해 두면 복습할 때 큰 도움이 됩니다.", ""]
        nav = []
        if i > 0:
            p = days[i - 1]
            nav.append(f"[← Day {p['n']} {p['title']}](day{p['n']:02d}.md)")
        nav.append("[목차](../README.md)")
        if i < total - 1:
            q = days[i + 1]
            nav.append(f"[Day {q['n']} {q['title']} →](day{q['n']:02d}.md)")
        L += ["---", "", " · ".join(nav), ""]
        open(os.path.join(POSTS, f"day{d['n']:02d}.md"), "w", encoding="utf-8").write("\n".join(L))

    R = ["# 📈 차트 공부 — 초보자를 위한 A to Z", "",
         "매일 아침 텔레그램으로 그날 분량(개념 10~20개)이 도착하고, 같은 내용이 아래 포스팅으로 정리됩니다.",
         "캔들 하나 읽는 법에서 시작해 추세·지지저항·거래량·보조지표·볼린저 밴드·리스크 관리까지 순서대로 갑니다.", "",
         f"총 **{total}일 · 개념 {sum(len(d['items']) for d in days)}개**", "",
         "| Day | 주제 | 개념 수 |", "|:-:|---|:-:|"]
    for d in days:
        R.append(f"| {d['n']} | [{d['title']}](posts/day{d['n']:02d}.md) | {len(d['items'])} |")
    R += ["", "## 단계별 흐름", "", "```mermaid", "flowchart LR",
          "  A[캔들·타임프레임<br/>Day 1-4] --> B[추세·추세선<br/>Day 5-6]",
          "  B --> C[지지저항·거래량<br/>Day 7-8]", "  C --> D[이동평균·차트패턴<br/>Day 9-11]",
          "  D --> E[보조지표·볼린저<br/>Day 12-14]", "  E --> F[피보나치·수급<br/>Day 15-16]",
          "  F --> G[리스크·심리<br/>Day 17-18]", "```", "",
          "## 파일 구성", "",
          "- `lessons.md` — 커리큘럼 원본 (이 파일만 고치면 포스팅·텔레그램이 같이 바뀜)",
          "- `posts/` — Day별 포스팅 (`python chart-study/study_bot.py build`로 생성)",
          "- `img/` — 개념 그림 (`python chart-study/make_figures.py`로 생성)",
          "- `progress.json` — 텔레그램 진도",
          "- 발송: `.github/workflows/chart-study.yml` (매일 아침 7시대)", ""]
    open(os.path.join(HERE, "README.md"), "w", encoding="utf-8").write("\n".join(R))
    print(f"포스팅 {total}개 + README 생성")


# ── 텔레그램 ────────────────────────────────────────
def messages(d: dict, total: int) -> tuple[str, list[str]]:
    caption = (f"📈 <b>차트 공부 Day {d['n']}/{total} · {html.escape(d['title'], quote=False)}</b>\n"
               f"{html.escape(d['intro'], quote=False)}\n\n"
               f"오늘 개념 {len(d['items'])}개 · <a href=\"{post_url(d['n'])}\">그림 포함 포스팅 보기</a>")
    blocks = [f"<b>{k}. {html.escape(it['term'], quote=False)}</b>\n{html.escape(it['desc'], quote=False)}"
              for k, it in enumerate(d["items"], 1)]
    chunks, cur = [], ""
    for b in blocks:
        if len(cur) + len(b) + 2 > 3800:
            chunks.append(cur); cur = ""
        cur += ("\n\n" if cur else "") + b
    if cur:
        chunks.append(cur)
    chunks[-1] += "\n\n✍️ <i>오늘의 연습: 관심 종목 차트에서 오늘 개념을 하나씩 찾아보세요.</i>"
    return caption, chunks


def tg(method: str, **kw):
    tok = (os.environ.get("TELEGRAM_TOKEN") or "").strip()
    chat = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    if not tok or not chat:
        sys.exit("::error::TELEGRAM_TOKEN / TELEGRAM_CHAT_ID 가 없습니다")
    if chat.startswith("-"):   # 그룹·채널 ID는 음수 — 공부 메시지는 개인 채팅에만
        sys.exit("::error::그룹방으로는 보내지 않습니다 (개인 채팅 ID만 허용)")
    files = kw.pop("files", None)
    for i in range(3):
        r = requests.post(f"https://api.telegram.org/bot{tok}/{method}", data={"chat_id": chat, **kw},
                          files=files, timeout=30)
        if r.ok:
            return r.json()
        print("텔레그램 실패", r.status_code, r.text[:300])
        if files:
            for f in files.values():
                f[1].seek(0)
        time.sleep(3)
    raise RuntimeError(f"텔레그램 {method} 실패")


def send_day(d: dict, total: int, dry=False):
    caption, chunks = messages(d, total)
    if dry:
        print(caption, "\n", *[f"\n----- 메시지 {i + 1} ({len(c)}자)\n{c}" for i, c in enumerate(chunks)])
        return
    img = os.path.join(HERE, d["images"][0]["path"]) if d["images"] else None
    if img and os.path.exists(img):
        with open(img, "rb") as f:
            tg("sendPhoto", caption=caption, parse_mode="HTML", files={"photo": (os.path.basename(img), f, "image/png")})
    else:
        tg("sendMessage", text=caption, parse_mode="HTML", disable_web_page_preview="true")
    for c in chunks:
        tg("sendMessage", text=c, parse_mode="HTML", disable_web_page_preview="true")
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
    if n > total:           # 다 끝나면 처음부터 복습 회차
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
