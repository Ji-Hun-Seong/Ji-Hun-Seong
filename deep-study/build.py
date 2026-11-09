#!/usr/bin/env python3
"""심화 글 검사 + 목록 생성.   python deep-study/build.py   실패하면 종료코드 1.

부족한 글이 올라가지 않도록 분량·문제·출처·분개 대차를 기계적으로 막는다."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "toss-bot" / "static"
APPS = ("fundroad", "masterroad")
MIN = {"sections": 8, "chars": 8000, "qs": 10, "src": 3}
BLOCKS = {"p", "ul", "tip", "calc", "j", "f", "table"}


def num(a):
    a = a.replace(",", "")
    return float(a) if re.fullmatch(r"-?\d+(\.\d+)?", a) else None


def text_of(block):
    return sum(len(str(v)) for v in block.values())


def check(path, t):
    e = []
    for k in ("id", "area", "t", "date", "sum", "intro", "sections", "qs", "src"):
        if not t.get(k):
            e.append(f"{k} 없음")
    if e:
        return e
    if t["id"] != path.stem or not re.fullmatch(r"\d{8}-[a-z0-9-]+", t["id"]):
        e.append("id는 파일 이름과 같고 YYYYMMDD-slug 형식")
    if len(t["sections"]) < MIN["sections"]:
        e.append(f"절 {len(t['sections'])}개 < {MIN['sections']}")
    chars = 0
    for s in t["sections"]:
        if not s.get("h") or not s.get("b"):
            e.append("절에 h·b 필요")
            continue
        for b in s["b"]:
            if len(b) != 1 or next(iter(b)) not in BLOCKS:
                e.append(f"모르는 블록 {list(b)[:2]}")
                continue
            chars += text_of(b)
            for r in b.get("j", []):
                if "note" in r:
                    continue
                if not r.get("dr") or not r.get("cr"):
                    e.append("분개에 차변·대변 필요")
                    continue
                dr, cr = [[num(a[1]) for a in r[x]] for x in ("dr", "cr")]
                if None not in dr + cr and abs(sum(dr) - sum(cr)) > 1:
                    e.append(f"분개 대차 불일치 {sum(dr)} != {sum(cr)}: {r['dr'][0][0]}")
            if "table" in b and any(len(r) != len(b["table"]["head"]) for r in b["table"]["rows"]):
                e.append("표의 열 수 불일치")
    if chars < MIN["chars"]:
        e.append(f"본문 {chars}자 < {MIN['chars']}")
    if len(t["qs"]) < MIN["qs"]:
        e.append(f"문제 {len(t['qs'])}개 < {MIN['qs']}")
    for q in t["qs"]:
        if len(q) != 3 or len(q[1]) != 4 or len(set(q[1])) != 4 or not q[2]:
            e.append(f"문제 형식 오류: {str(q[0])[:30]}")
    if len(t["src"]) < MIN["src"]:
        e.append(f"출처 {len(t['src'])}개 < {MIN['src']}")
    if any(not str(s.get("u", "")).startswith("http") or not s.get("t") for s in t["src"]):
        e.append("출처에 t와 http 주소 필요")
    t["_chars"] = chars
    return e


def main():
    bad = 0
    for app in APPS:
        items = []
        for path in sorted((ROOT / app / "deep" / "topics").glob("*.json")):
            t = json.loads(path.read_text(encoding="utf-8"))
            errs = check(path, t)
            for x in errs:
                print(f"❌ {app}/{path.name}: {x}")
            bad += len(errs)
            if not errs:
                items.append({"id": t["id"], "area": t["area"], "t": t["t"], "date": t["date"], "sum": t["sum"],
                              "n_sections": len(t["sections"]), "n_qs": len(t["qs"]), "chars": t["_chars"]})
        items.sort(key=lambda m: m["id"], reverse=True)
        out = json.dumps({"topics": items}, ensure_ascii=False, indent=0)
        (ROOT / app / "deep" / "index.json").write_text(out + "\n", encoding="utf-8")
        print(f"{app}: 주제 {len(items)}개, {sum(m['chars'] for m in items):,}자")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
