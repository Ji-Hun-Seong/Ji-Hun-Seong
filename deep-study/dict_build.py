#!/usr/bin/env python3
"""백과 항목 검사 + 합치기.   python deep-study/dict_build.py   실패하면 종료코드 1.

<앱>/dict/src/*.json (항목 하나당 파일 하나) → <앱>/dict/terms.json (앱이 읽는 파일)."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "toss-bot" / "static"
APPS = ("masterroad", "fundroad")
BLOCKS = {"p", "ul", "tip", "calc", "j", "f", "table", "hero", "kv", "tl", "pts", "donut", "pc", "branch", "callout", "ex", "chain", "flow"}
MIN_SEC, MIN_CHARS = 2, 300


def norm(s):
    return re.sub(r"[\s·・()\[\]{}'\"’‘“”,.\-_/]", "", str(s or "").lower())


def text(b):
    return sum(len(json.dumps(v, ensure_ascii=False)) for v in b.values())


def check_app(app):
    src = ROOT / app / "dict" / "src"
    if not src.exists():
        return 0, []
    errs, terms, keys = [], [], {}
    for p in sorted(src.glob("*.json")):
        try:
            e = json.loads(p.read_text())
        except Exception as x:
            errs.append(f"{p.name}: JSON 오류 {x}")
            continue
        err = lambda m: errs.append(f"{app}/{p.name}: {m}")
        for k in ("id", "k", "area", "one", "sec", "upd"):
            if not e.get(k):
                err(f"{k} 없음")
        if e.get("id") != p.stem or not re.fullmatch(r"[a-z0-9-]+", p.stem):
            err("id는 파일 이름과 같고 영문 소문자·숫자·하이픈")
        if len(e.get("sec", [])) < MIN_SEC:
            err(f"절 {len(e.get('sec', []))}개 < {MIN_SEC}")
        chars = len(e.get("one", ""))
        for s in e.get("sec", []):
            if not s.get("h") or not s.get("b"):
                err("절에 h·b 필요")
                continue
            for b in s["b"]:
                if len(b) != 1 or next(iter(b)) not in BLOCKS:
                    err(f"모르는 블록 {list(b)[:2]}")
                    continue
                chars += text(b)
                if "table" in b and any(len(r) != len(b["table"]["head"]) for r in b["table"]["rows"]):
                    err(f"표 열 수 불일치: {b['table']['head']}")
        if chars < MIN_CHARS:
            err(f"본문 {chars}자 < {MIN_CHARS}")
        for k in [e.get("k"), *e.get("al", []), *e.get("al2", []), e.get("en")]:
            if not k:
                continue
            n = norm(k)
            if n in keys and keys[n] != e.get("id"):
                err(f"이름 '{k}'이(가) {keys[n]} 항목과 겹침")
            keys.setdefault(n, e.get("id"))
        e["_chars"] = chars
        terms.append(e)
    for e in terms:
        for r in e.get("rel", []):
            if norm(r) not in keys:
                errs.append(f"{app}/{e['id']}: 관련 항목 '{r}' 없음 (아직 없는 항목이면 빼거나 먼저 쓴다)")
    if errs:
        return len(terms), errs
    total = sum(e.pop("_chars") for e in terms)
    terms.sort(key=lambda e: e["k"])
    out = {"n": len(terms), "chars": total, "areas": sorted({e["area"] for e in terms}), "terms": terms}
    (ROOT / app / "dict" / "terms.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print(f"{app}: 항목 {len(terms)}개 · 본문 약 {total:,}자 · 분야 {len(out['areas'])}개")
    return len(terms), []


def main():
    bad = []
    for app in APPS:
        _, e = check_app(app)
        bad += e
    if bad:
        print("\n".join(bad))
        sys.exit(1)


if __name__ == "__main__":
    main()
