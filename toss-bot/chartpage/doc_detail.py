"""
doc_detail.py — 대시보드에서 공시·증권사 리포트를 눌렀을 때 앱 안에서 보여 줄 상세 내용

  공시     : DART 원문 API(document.xml, zip) → 표·문단으로 정리 + 핵심 항목 요약     ← DART_API_KEY
  리포트   : 네이버 금융 리서치 상세(company_read) → 목표가·투자의견·요약 본문·PDF 링크

단독 테스트:  python3 doc_detail.py filing 20261029000123      python3 doc_detail.py research 81234
"""
from __future__ import annotations

import html
import io
import json
import os
import re
import sys
import zipfile
from html.parser import HTMLParser

import requests

UA = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
                    "Version/17.0 Mobile/15E148 Safari/604.1"}
MAX_BLOCKS = 220          # 분기·사업보고서처럼 긴 문서는 앞부분만
MAX_CELL = 400


def _sp(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


# ── 공시: DART XML → 블록 ─────────────────────────────
class _DartParser(HTMLParser):
    """DART 원문 XML(형식이 느슨해서 HTMLParser로 관대하게 읽음) → [{t:h|p|table, ...}]"""
    CELL = {"td", "th", "tu", "te"}
    HEAD = {"title", "document-name", "cover-title"}
    SKIP = {"style", "script", "extraction", "image", "img", "library"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks, self.buf = [], []
        self.tables = []          # 중첩 표 스택: 각 항목 = {"rows": [...], "row": [...] | None, "cell": [...] | None}
        self.skip = 0
        self.head = 0

    # 문단 텍스트 비우기
    def _flush(self, kind="p"):
        t = _sp("".join(self.buf))
        self.buf = []
        if t and not self.tables:
            if self.blocks and self.blocks[-1]["t"] == kind and self.blocks[-1]["text"] == t:
                return
            self.blocks.append({"t": kind, "text": t[:2000]})

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
            return
        if self.skip:
            return
        if tag == "table":
            self._flush()
            self.tables.append({"rows": [], "row": None, "cell": None})
        elif self.tables and tag == "tr":
            self.tables[-1]["row"] = []
        elif self.tables and tag in self.CELL:
            tb = self.tables[-1]
            if tb["row"] is None:
                tb["row"] = []
            tb["cell"] = []
        elif tag in ("br",):
            self._data("\n" if self.tables else " ")
        elif tag in self.HEAD:
            self._flush()
            self.head += 1
        elif tag in ("p", "section-1", "section-2", "section-3", "pgbrk"):
            if not self.tables:
                self._flush()

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if not self.tables:
            if tag in self.HEAD:
                self.head = max(0, self.head - 1)
                self._flush("h")
            elif tag == "p":
                self._flush()
            return
        tb = self.tables[-1]
        if tag in self.CELL and tb["cell"] is not None:
            tb["row"].append(_sp("".join(tb["cell"]))[:MAX_CELL])
            tb["cell"] = None
        elif tag == "tr" and tb["row"] is not None:
            if tb["cell"] is not None:                       # </td> 빠진 경우
                tb["row"].append(_sp("".join(tb["cell"]))[:MAX_CELL])
                tb["cell"] = None
            if any(tb["row"]):
                tb["rows"].append(tb["row"])
            tb["row"] = None
        elif tag == "table":
            self.tables.pop()
            rows = tb["rows"]
            if self.tables:                                  # 표 안의 표 → 바깥 칸에 글자로 붙임
                outer = self.tables[-1]
                if outer["cell"] is not None:
                    outer["cell"].append(" / ".join(" ".join(c for c in r if c) for r in rows))
                return
            if rows:
                self.blocks.append({"t": "table", "rows": rows[:120]})

    def _data(self, d):
        if self.skip:
            return
        if self.tables:
            tb = self.tables[-1]
            if tb["cell"] is not None:
                tb["cell"].append(d)
        else:
            self.buf.append(d)

    def handle_data(self, d):
        self._data(d)

    def close(self):
        super().close()
        self._flush()


def parse_dart_xml(text: str) -> list[dict]:
    p = _DartParser()
    p.feed(text)
    p.close()
    out = []
    for b in p.blocks:
        if b["t"] == "table":                                # 빈 열 정리
            w = max(len(r) for r in b["rows"])
            rows = [r + [""] * (w - len(r)) for r in b["rows"]]
            keep = [i for i in range(w) if any(r[i] for r in rows)]
            b["rows"] = [[r[i] for i in keep] for r in rows]
            if not b["rows"] or not keep:
                continue
        out.append(b)
        if len(out) >= MAX_BLOCKS:
            break
    return out


# 공시 종류와 상관없이 많이 보는 항목 → '핵심 요약'
FACT_KEYS = [
    r"계약금액|계약\s*금액", r"매출액\s*대비", r"최근\s*매출액", r"계약상대", r"계약\s*기간|시작일|종료일", r"판매.*공급계약\s*내용|계약\s*내용|체결계약명",
    r"취득예정주식|취득\s*예정\s*주식", r"취득예정금액|취득\s*예정\s*금액", r"취득예상기간|취득\s*기간|계약기간", r"취득목적|목적",
    r"1주당\s*배당금", r"시가배당률", r"배당금\s*총액", r"배당기준일",
    r"^매출액", r"영업이익", r"당기순이익",
    r"투자금액", r"자기자본\s*대비", r"투자목적", r"신주의\s*종류와\s*수|발행가액|발행할\s*주식",
    r"소유주식수|보유주식|소유비율|보유비율|변동사유|보고사유",
    r"양수금액|양도금액|처분금액|처분주식|소각할\s*주식",
]


def key_facts(blocks: list[dict], limit: int = 8) -> list[dict]:
    facts, seen, num = [], set(), re.compile(r"^[\d가-하]{1,2}[.)]\s*")
    for b in blocks:
        if b["t"] != "table":
            continue
        group = ""
        for r in b["rows"]:
            cells = [c for c in r if c]
            if len(cells) < 2:
                continue
            if len(cells) > 2:
                group = num.sub("", cells[0])
            elif num.match(cells[0]):                                  # '3. 계약상대' 같은 새 항목
                group = ""
            value, label = cells[-1], num.sub("", cells[-2])
            if len(label) <= 5 and group and group != label:          # '시작일' → '계약기간 시작일'
                label = f"{group} {label}"
            if not value or value in ("-", "—") or len(value) > 120 or len(label) > 60 or label in seen:
                continue
            flat = label.replace(" ", "")
            if any(re.search(k, flat) or re.search(k, label) for k in FACT_KEYS):
                seen.add(label)
                facts.append({"k": label, "v": value})
                if len(facts) >= limit:
                    return facts
    return facts


def _decode(b: bytes) -> str:
    for enc in ("utf-8", "cp949"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            pass
    return b.decode("utf-8", "replace")


def filing_detail(rcept_no: str) -> dict:
    rcept_no = re.sub(r"\D", "", rcept_no or "")
    if len(rcept_no) != 14:
        return {"error": "접수번호가 올바르지 않음"}
    url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"
    out = {"kind": "filing", "id": rcept_no, "url": url}
    key = os.environ.get("DART_API_KEY") or os.environ.get("DART_KEY")
    if not key:
        return {**out, "error": "DART_API_KEY가 없어 원문을 못 가져옴"}
    r = requests.get("https://opendart.fss.or.kr/api/document.xml", params={"crtfc_key": key, "rcept_no": rcept_no},
                     headers=UA, timeout=25)
    r.raise_for_status()
    if not r.content.startswith(b"PK"):                      # 오류면 zip이 아니라 상태 XML
        m = re.search(rb"<message>(.*?)</message>", r.content)
        return {**out, "error": "DART: " + (_decode(m.group(1)) if m else "원문 없음")}
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = sorted(z.namelist(), key=lambda n: (not n.startswith(rcept_no + ".") and n != f"{rcept_no}.xml", len(n), n))
    blocks, attach = [], []
    for i, n in enumerate(names):
        if not n.lower().endswith(".xml"):
            continue
        bl = parse_dart_xml(_decode(z.read(n)))
        if i == 0 or not blocks:
            blocks = bl
        else:
            title = next((b["text"] for b in bl if b["t"] == "h"), n)
            attach.append(title[:60])
    title = next((b["text"] for b in blocks if b["t"] == "h"), "")
    return {**out, "title": title, "facts": key_facts(blocks), "blocks": blocks,
            "truncated": len(blocks) >= MAX_BLOCKS, "attachments": attach}


# ── 리포트: 네이버 금융 리서치 상세 ───────────────────────
def _strip(h: str) -> str:
    h = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", h)
    h = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>", "\n", h)
    h = re.sub(r"(?i)<li[^>]*>", "• ", h)
    t = html.unescape(re.sub(r"<[^>]+>", "", h)).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", l).strip() for l in t.split("\n")]
    out = []
    for l in lines:
        if l or (out and out[-1]):
            out.append(l)
    return "\n".join(out).strip()


def research_detail(nid: str) -> dict:
    nid = re.sub(r"\D", "", str(nid or ""))
    if not nid:
        return {"error": "리포트 번호가 올바르지 않음"}
    out = {"kind": "research", "id": nid, "url": f"https://m.stock.naver.com/research/company/{nid}"}
    r = requests.get("https://finance.naver.com/research/company_read.naver", params={"nid": nid}, headers=UA, timeout=15)
    r.raise_for_status()
    h = _decode(r.content) if b'charset="utf-8"' in r.content[:3000].lower() else r.content.decode("cp949", "replace")

    m = re.search(r'(?is)<th[^>]*class="view_sbj"[^>]*>(.*?)</th>', h)
    if m:
        sbj = m.group(1)
        src = re.search(r'(?is)<p[^>]*class="source"[^>]*>(.*?)</p>', sbj)
        out["title"] = _sp(_strip(re.sub(r'(?is)<(p|span)[^>]*class="(source|stock)"[^>]*>.*?</\1>', "", sbj)))
        stock = re.search(r'(?is)<span[^>]*class="stock"[^>]*>(.*?)</span>', sbj)
        if stock:
            out["stock"] = _sp(_strip(stock.group(1)))
        if src:
            parts = [p.strip() for p in _strip(src.group(1)).split("|") if p.strip()]
            if parts:
                out["broker"] = parts[0]
            d = next((p for p in parts if re.match(r"\d{4}\.\d{2}\.\d{2}", p)), None)
            if d:
                out["date"] = d
    money = re.search(r'(?is)class="money"[^>]*>(.*?)</em>', h)
    if money:
        out["target"] = _sp(_strip(money.group(1)))
    com = re.search(r'(?is)class="coment"[^>]*>(.*?)</em>', h)
    if com:
        out["opinion"] = _sp(_strip(com.group(1)))
    body = re.search(r'(?is)<td[^>]*class="view_cnt"[^>]*>(.*?)</td>', h)
    if body:
        out["body"] = _strip(body.group(1))[:8000]
    pdf = re.search(r'https?://[^"\'\s>]+\.pdf', h)
    if pdf:
        out["pdf"] = pdf.group(0)
    if not out.get("body") and not out.get("title"):
        out["error"] = "리포트 내용을 읽지 못함 — 원문 링크로 열어 보세요"
    return out


def detail(kind: str, id_: str) -> dict:
    if kind == "filing":
        return filing_detail(id_)
    if kind == "research":
        return research_detail(id_)
    return {"error": "알 수 없는 종류"}


if __name__ == "__main__":
    print(json.dumps(detail(sys.argv[1], sys.argv[2]), ensure_ascii=False, indent=1)[:6000])
