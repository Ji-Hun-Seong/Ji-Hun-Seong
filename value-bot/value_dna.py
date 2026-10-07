"""
value_dna.py — 매매일지에서 '투자 DNA'를 뽑아내는 모듈

미래에셋 '기간별 매매일지' CSV(cp949 또는 utf-8)를 읽어
  1) 종목별 매수/매도/손익을 합산하고
  2) 종목 분류표(TAXONOMY)로 시장·유형·업종·그룹을 붙인 뒤
  3) 자금 비중 + 수익 기여 + 최근성 가중으로 성향 점수(affinity)를 계산한다.
"""
from __future__ import annotations

import csv
import glob
import io
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# 1. 지금까지 매매한 종목 분류표
#    market: KOSPI / KOSDAQ   kind: holdco(지주·지주형) / pref(우선주) / operating
#    매매일지에 새 종목이 생기면 여기에 한 줄 추가하면 된다.
# ---------------------------------------------------------------------------
TAXONOMY: dict[str, dict] = {
    "대덕GDS":        dict(market="KOSPI",  kind="operating", sector="전자·IT",           group="대덕"),
    "대덕GDS우":      dict(market="KOSPI",  kind="pref",      sector="전자·IT",           group="대덕"),
    "대덕1우":        dict(market="KOSPI",  kind="pref",      sector="전자·IT",           group="대덕"),
    "세방":           dict(market="KOSPI",  kind="holdco",    sector="산업재·기계·건설",  group="세방"),
    "세방전지":       dict(market="KOSPI",  kind="operating", sector="자동차·부품",       group="세방"),
    "경동인베스트":   dict(market="KOSPI",  kind="holdco",    sector="산업재·기계·건설",  group="경동"),
    "하이록코리아":   dict(market="KOSDAQ", kind="operating", sector="산업재·기계·건설",  group="하이록"),
    "지엠비코리아":   dict(market="KOSPI",  kind="operating", sector="자동차·부품",       group="지엠비"),
    "SBS":            dict(market="KOSPI",  kind="operating", sector="미디어",            group="태영"),
    "SBS미디어홀딩스":dict(market="KOSPI",  kind="holdco",    sector="미디어",            group="태영"),
    "LF":             dict(market="KOSPI",  kind="operating", sector="유통·소비재",       group="LF"),
    "아세아시멘트":   dict(market="KOSPI",  kind="operating", sector="철강·시멘트·제지",  group="아세아"),
    "아세아제지":     dict(market="KOSPI",  kind="operating", sector="철강·시멘트·제지",  group="아세아"),
    "세아베스틸지주": dict(market="KOSPI",  kind="holdco",    sector="철강·시멘트·제지",  group="세아"),
    "유화증권":       dict(market="KOSPI",  kind="operating", sector="금융·보험",         group="유화"),
    "DN오토모티브":   dict(market="KOSPI",  kind="operating", sector="자동차·부품",       group="DN"),
    "KT":             dict(market="KOSPI",  kind="operating", sector="통신·유틸·에너지",  group="KT"),
    "SK텔레콤":       dict(market="KOSPI",  kind="operating", sector="통신·유틸·에너지",  group="SK"),
    "현대백화점":     dict(market="KOSPI",  kind="operating", sector="유통·소비재",       group="현대백화점"),
    "현대홈쇼핑":     dict(market="KOSPI",  kind="operating", sector="유통·소비재",       group="현대백화점"),
    "현대지에프홀딩스":dict(market="KOSPI", kind="holdco",    sector="유통·소비재",       group="현대백화점"),
    "한화생명":       dict(market="KOSPI",  kind="operating", sector="금융·보험",         group="한화"),
    "현대해상":       dict(market="KOSPI",  kind="operating", sector="금융·보험",         group="현대해상"),
    "KPX홀딩스":      dict(market="KOSPI",  kind="holdco",    sector="화학·소재",         group="KPX"),
    "KPX케미칼":      dict(market="KOSPI",  kind="operating", sector="화학·소재",         group="KPX"),
    "코오롱인더우":   dict(market="KOSPI",  kind="pref",      sector="화학·소재",         group="코오롱"),
    "롯데케미칼":     dict(market="KOSPI",  kind="operating", sector="화학·소재",         group="롯데"),
    "현대차3우B":     dict(market="KOSPI",  kind="pref",      sector="자동차·부품",       group="현대차"),
    "리드코프":       dict(market="KOSDAQ", kind="operating", sector="금융·보험",         group="리드코프"),
    "대창단조":       dict(market="KOSDAQ", kind="operating", sector="산업재·기계·건설",  group="대창단조"),
    "KT&G":           dict(market="KOSPI",  kind="operating", sector="유통·소비재",       group="KT&G"),
    "한양이엔지":     dict(market="KOSDAQ", kind="operating", sector="산업재·기계·건설",  group="한양이엔지"),
    "이마트":         dict(market="KOSPI",  kind="operating", sector="유통·소비재",       group="신세계"),
    "슈프리마":       dict(market="KOSDAQ", kind="operating", sector="전자·IT",           group="슈프리마"),
    "동아타이어":     dict(market="KOSPI",  kind="operating", sector="자동차·부품",       group="동아타이어"),
    "쿠쿠홈시스":     dict(market="KOSPI",  kind="operating", sector="유통·소비재",       group="쿠쿠"),
    "코웨이":         dict(market="KOSPI",  kind="operating", sector="유통·소비재",       group="넷마블"),
    "강원랜드":       dict(market="KOSPI",  kind="operating", sector="유통·소비재",       group="강원랜드"),
    "DL":             dict(market="KOSPI",  kind="holdco",    sector="산업재·기계·건설",  group="DL"),
    "삼성전자":       dict(market="KOSPI",  kind="operating", sector="전자·IT",           group="삼성"),
    "금화피에스시":   dict(market="KOSDAQ", kind="operating", sector="산업재·기계·건설",  group="금화"),
}

# 기간이 최근일수록 '앞으로의 취향'을 더 잘 설명한다고 보고 가중치를 키운다.
RECENCY = {"2017": 0.60, "2019": 0.70, "2021": 0.85, "2023": 1.00, "2025": 1.15}

# 코스피 상장 종목 라인 구성비(대략): 우선주 ~12%, 지주·지주형 ~8%, 나머지 사업회사
KIND_BASELINE = {"operating": 0.80, "holdco": 0.08, "pref": 0.12}


@dataclass
class Position:
    name: str
    buy_qty: int = 0
    buy_amt: int = 0
    sell_qty: int = 0
    sell_amt: int = 0
    pnl: int = 0
    w_buy: float = 0.0          # 최근성 가중 매수금액
    w_pnl: float = 0.0          # 최근성 가중 손익
    periods: set = field(default_factory=set)
    leveraged: bool = False     # '(대출)' 매매 존재 여부

    @property
    def net_qty(self) -> int:
        return self.buy_qty - self.sell_qty


def _read_text(path: str) -> str:
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"인코딩을 알 수 없음: {path}")


def _to_int(s: str) -> int:
    s = (s or "").replace(",", "").strip()
    return int(float(s)) if s else 0


def load_journals(folder: str) -> dict[str, Position]:
    """폴더 안의 *매매일지*.csv 를 모두 읽어 종목별로 합산한다."""
    files = sorted(glob.glob(os.path.join(folder, "*.csv")))
    if not files:
        raise FileNotFoundError(f"{folder} 에 CSV가 없습니다.")
    book: dict[str, Position] = {}
    for path in files:
        m = re.search(r"(20\d\d)", os.path.basename(path))
        period = m.group(1) if m else "2025"
        rw = RECENCY.get(period, 1.0)
        rows = list(csv.reader(io.StringIO(_read_text(path))))
        for r in rows[2:]:                      # 헤더 2줄
            if not r or not r[0].strip():
                continue
            raw_name = r[0].strip()
            leveraged = "(대출)" in raw_name
            name = raw_name.replace("(대출)", "").strip()
            p = book.setdefault(name, Position(name))
            bq, ba = _to_int(r[1]), _to_int(r[3])
            sq, sa = _to_int(r[4]), _to_int(r[6])
            pnl = _to_int(r[8])
            p.buy_qty += bq; p.buy_amt += ba
            p.sell_qty += sq; p.sell_amt += sa
            p.pnl += pnl
            p.w_buy += ba * rw
            p.w_pnl += pnl * rw
            p.periods.add(period)
            p.leveraged |= leveraged
    return book


@dataclass
class DNA:
    book: dict
    kind_aff: dict        # 0~1 정규화된 유형 선호
    sector_aff: dict      # 0~1 정규화된 업종 선호
    group_aff: dict       # 그룹별 선호(0~1)
    market_share: dict    # 시장별 매수금액 비중
    kind_share: dict      # 유형별 매수금액 비중(가중 전)
    sector_share: dict
    tag_pnl: dict         # (축, 값) -> 실현손익
    holdings: list        # 현재 보유로 추정되는 종목
    traded: set
    unknown: list         # 분류표에 없는 종목
    win_rate: float
    leverage_pnl: int
    total_buy: int
    total_pnl: int


def _normalize(d: dict) -> dict:
    mx = max(d.values()) if d else 0
    return {k: (v / mx if mx > 0 else 0) for k, v in d.items()}


def build_dna(book: dict[str, Position]) -> DNA:
    unknown = [n for n in book if n not in TAXONOMY]
    w_cap = {"kind": defaultdict(float), "sector": defaultdict(float), "group": defaultdict(float)}
    w_win = {"kind": defaultdict(float), "sector": defaultdict(float), "group": defaultdict(float)}
    market_share, kind_share, sector_share = defaultdict(float), defaultdict(float), defaultdict(float)
    tag_pnl = defaultdict(int)
    total_buy = sum(p.buy_amt for p in book.values())

    for n, p in book.items():
        t = TAXONOMY.get(n)
        if not t:
            continue
        market_share[t["market"]] += p.buy_amt
        kind_share[t["kind"]] += p.buy_amt
        sector_share[t["sector"]] += p.buy_amt
        for axis in ("kind", "sector", "group"):
            # 매수금액이 0(기존 보유분 매도)인 종목도 매도금액으로 존재감을 반영
            presence = p.w_buy if p.w_buy > 0 else p.sell_amt * 0.5
            w_cap[axis][t[axis]] += presence
            w_win[axis][t[axis]] += max(p.w_pnl, 0)
            tag_pnl[(axis, t[axis])] += p.pnl
        tag_pnl[("market", t["market"])] += p.pnl

    def blend(axis, baseline=None):
        cap_raw = dict(w_cap[axis])
        if baseline:
            # 유형은 시장 구성비 대비 '얼마나 과하게 담았나'(lift)로 본다.
            # 코스피 상장 라인의 대부분은 일반 사업회사이므로 금액만 보면 operating이 늘 1등이 된다.
            s = sum(cap_raw.values()) or 1
            cap_raw = {k: (v / s) / baseline.get(k, 1) for k, v in cap_raw.items()}
        cap, win = _normalize(cap_raw), _normalize(w_win[axis])
        keys = set(cap) | set(win)
        # 자금을 얼마나 실었나 60% + 실제로 돈을 벌었나 40%
        return _normalize({k: 0.6 * cap.get(k, 0) + 0.4 * win.get(k, 0) for k in keys})

    tot = lambda d: {k: v / total_buy for k, v in d.items()} if total_buy else {}
    closed = [p for p in book.values() if p.sell_amt > 0]
    wins = [p for p in closed if p.pnl > 0]
    holdings = sorted([p.name for p in book.values() if p.net_qty > 0 and p.buy_qty > 0],
                      key=lambda n: -book[n].buy_amt)
    lev = sum(p.pnl for p in book.values() if p.leveraged)
    return DNA(
        book=book,
        kind_aff=blend("kind", KIND_BASELINE), sector_aff=blend("sector"), group_aff=blend("group"),
        market_share=tot(market_share), kind_share=tot(kind_share), sector_share=tot(sector_share),
        tag_pnl=dict(tag_pnl), holdings=holdings, traded=set(book), unknown=unknown,
        win_rate=len(wins) / len(closed) if closed else 0,
        leverage_pnl=lev, total_buy=total_buy, total_pnl=sum(p.pnl for p in book.values()),
    )


def export_profile(dna: DNA, path: str):
    """금액 없이 '취향'만 담은 프로필을 저장한다(공개 저장소에 올려도 매매 금액이 드러나지 않음)."""
    import json
    groups = {g: (1 if v > 0 else -1) for (axis, g), v in dna.tag_pnl.items() if axis == "group" and v}
    json.dump({
        "kind_aff": dna.kind_aff, "sector_aff": dna.sector_aff, "group_aff": dna.group_aff,
        "group_result": groups, "traded": sorted(dna.traded), "holdings": dna.holdings,
    }, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def load_profile(path: str) -> DNA:
    import json
    p = json.load(open(path, encoding="utf-8"))
    return DNA(
        book={}, kind_aff=p["kind_aff"], sector_aff=p["sector_aff"], group_aff=p["group_aff"],
        market_share={}, kind_share={}, sector_share={},
        tag_pnl={("group", g): v for g, v in p["group_result"].items()},
        holdings=p["holdings"], traded=set(p["traded"]), unknown=[],
        win_rate=0, leverage_pnl=0, total_buy=0, total_pnl=0,
    )


def kosdaq_names(book) -> list[str]:
    return [n for n in book if TAXONOMY.get(n, {}).get("market") == "KOSDAQ"]


if __name__ == "__main__":
    import sys
    d = build_dna(load_journals(sys.argv[1] if len(sys.argv) > 1 else "journals"))
    print("시장 비중:", {k: f"{v:.1%}" for k, v in d.market_share.items()})
    print("유형 비중:", {k: f"{v:.1%}" for k, v in d.kind_share.items()})
    print("유형 선호:", {k: round(v, 2) for k, v in sorted(d.kind_aff.items(), key=lambda x: -x[1])})
    print("업종 선호:", {k: round(v, 2) for k, v in sorted(d.sector_aff.items(), key=lambda x: -x[1])})
    print("그룹 선호 TOP8:", sorted(d.group_aff.items(), key=lambda x: -x[1])[:8])
    print("현재 보유 추정:", d.holdings)
    print("코스닥 매매:", kosdaq_names(d.book))
    print(f"승률 {d.win_rate:.0%}, 총 실현손익 {d.total_pnl:,}원, 대출매매 손익 {d.leverage_pnl:,}원")
    print("미분류:", d.unknown)
