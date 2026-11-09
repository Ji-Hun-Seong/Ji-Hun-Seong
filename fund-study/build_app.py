#!/usr/bin/env python3
"""펀드회계 백과 원본(lessons_*.md)을 펀드로드 앱 데이터로 바꾼다.

    python fund-study/build_app.py   → toss-bot/static/fundroad/data.js

원본 내용을 고치면 이 스크립트만 다시 돌리면 된다. 확인 문제는 fundroad/quiz.js 에 따로 있다.
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "toss-bot" / "static" / "fundroad" / "data.js"

LEVELS = [
    (1, "펀드의 뼈대", "구조와 회계 원리", "기준가·순자산·발생주의·시가평가", 1, 2),
    (2, "주식", "매매와 기업행위", "매매·배당·증자·감자·합병·분할", 3, 8),
    (3, "채권·단기자금", "이자와 평가", "경과이자·콜론·RP·CP·MMF", 9, 12),
    (4, "설정·환매·보수", "돈이 드나드는 길", "원본·조정금·보수·클래스", 13, 14),
    (5, "파생·외화", "일일정산과 환율", "선물·옵션·스왑·선물환·해외자산", 15, 16),
    (6, "대체자산", "시가 없는 자산", "부동산·비상장·재간접·공정가치", 17, 18),
    (7, "결산·검증", "마감과 통제", "이익분배·과표·기준가 오류·대사", 19, 20),
]

AMOUNT = r"(?:[\d,]+(?:억|달러)?(?:\s*상당)?|xxx|원금\+이자)"
ENTRY = re.compile(r"^\s*(?P<pre>.*?)\s*차\)\s*(?P<dr>.*?)\s*(?:/\s*)?대\)\s*(?P<cr>.*)$")
ACCOUNT = re.compile(rf"^(?P<n>.*?)\s+(?P<a>{AMOUNT})\s*(?P<note>\(.*\))?$")
NODE = r"(\w+)(?:\[(.*?)\]|\{(.*?)\})?"
LINK = r"\s*(--\s*[^->]+?\s*-->|-->|-\.\s*[^.]+?\s*\.-)\s*"


def account(text):
    text = text.strip()
    m = ACCOUNT.match(text)
    if m:
        return [m["n"].strip(), m["a"], (m["note"] or "").strip()]
    return [text, "", ""]


def side(text):
    return [account(p) for p in text.split(" / ") if p.strip()]


def journal(lines):
    """분개 블록을 차변·대변 표로. 분개가 아닌 줄(계산식·설명)은 note로 둔다."""
    rows, last = [], None
    for raw in lines:
        if not raw.strip():
            continue
        m = ENTRY.match(raw)
        if m:
            last = {"pre": m["pre"].rstrip(": ").strip(), "dr": side(m["dr"]), "cr": side(m["cr"])}
            rows.append(last)
            continue
        indent = len(raw) - len(raw.lstrip())
        if last is not None and indent >= 4:
            parts = re.split(r"\s{3,}", raw.strip())
            if indent >= 12:
                last["cr"].append(account(" ".join(parts)))
            elif len(parts) == 4:
                last["dr"].append(account(" ".join(parts[:2])))
                last["cr"].append(account(" ".join(parts[2:])))
            else:
                last["dr"].append(account(" ".join(parts)))
            continue
        last = None
        rows.append({"note": raw.strip()})
    return rows


def label(groups):
    return re.sub(r"\s*<br/>\s*", " · ", groups or "").strip()


def flow(lines):
    """mermaid를 앱에서 그릴 수 있게 순서 목록 또는 연결 목록으로 바꾼다."""
    names, edges = {}, []
    for line in lines[1:]:
        line = line.strip()
        pos = 0
        m = re.match(NODE, line)
        if not m:
            continue
        cur = m[1]
        if m[2] or m[3]:
            names[cur] = label(m[2] or m[3])
        pos = m.end()
        while True:
            lk = re.match(LINK, line[pos:])
            if not lk:
                break
            pos += lk.end()
            n = re.match(NODE, line[pos:])
            pos += n.end()
            if n[2] or n[3]:
                names[n[1]] = label(n[2] or n[3])
            raw = lk[1]
            text = "" if raw == "-->" else re.sub(r"^--\s*|\s*-->$|^-\.\s*|\s*\.-$", "", raw)
            edges.append((cur, text, n[1], raw.startswith("-.")))
            cur = n[1]
    out = {e[0] for e in edges}
    linear = len(out) == len(edges) and len({e[2] for e in edges}) == len(edges) and not any(e[1] for e in edges)
    if linear:
        order = [edges[0][0]] + [e[2] for e in edges]
        return {"steps": [names.get(k, k) for k in order]}
    return {"edges": [[names.get(a, a), t, names.get(b, b), bool(d)] for a, t, b, d in edges]}


def parse():
    days, day, item = [], None, None
    src = "\n".join((HERE / f).read_text(encoding="utf-8") for f in ("lessons_1.md", "lessons_2.md")).split("\n")
    i = 0
    while i < len(src):
        line = src[i]
        i += 1
        m = re.match(r"^## Day (\d+) · (.+)$", line)
        if m:
            day = {"id": int(m[1]), "t": m[2].strip(), "intro": "", "flow": None, "items": []}
            days.append(day)
            item = None
            continue
        if day is None:
            continue
        if line.startswith("### "):
            item = {"t": line[4:].strip(), "b": []}
            day["items"].append(item)
            continue
        if line.startswith("> "):
            day["intro"] = line[2:].strip()
            continue
        if line.startswith("```"):
            kind = line[3:].strip()
            body = []
            while not src[i].startswith("```"):
                body.append(src[i])
                i += 1
            i += 1
            if kind == "mermaid":
                if item:
                    item["b"].append({"f": flow(body)})
                else:
                    day["flow"] = flow(body)
            else:
                item["b"].append({"j": journal(body)})
            continue
        if not line.strip() or item is None:
            continue
        if line.startswith("- "):
            if not item["b"] or "ul" not in item["b"][-1]:
                item["b"].append({"ul": []})
            item["b"][-1]["ul"].append(line[2:].strip())
        else:
            item["b"].append({"p": line.strip()})
    return days


def main():
    days = parse()
    for d in days:
        d["lv"] = next(l[0] for l in LEVELS if l[4] <= d["id"] <= l[5])
    levels = [{"id": l[0], "name": l[1], "title": l[2], "desc": l[3]} for l in LEVELS]
    data = json.dumps({"levels": levels, "days": days}, ensure_ascii=False, separators=(",", ":"))
    OUT.write_text("/* build_app.py가 fund-study/lessons_*.md에서 만든 파일 — 직접 고치지 말 것 */\nwindow.FR=" + data + ";\n", encoding="utf-8")
    print(f"{OUT.name}: Day {len(days)}개, 항목 {sum(len(d['items']) for d in days)}개")


if __name__ == "__main__":
    main()
