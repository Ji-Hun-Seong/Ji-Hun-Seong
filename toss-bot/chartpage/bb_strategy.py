"""
bb_strategy.py — 『Bollinger on Bollinger Bands』 기법 + 자사주 공시 + 외국인 수급 AND 필터

입력은 전부 pandas DataFrame이라 데이터 출처(토스 캔들, KIS 등)와 무관하게 씁니다.
  ohlcv : index=날짜(DatetimeIndex, 오름차순), columns = open, high, low, close, volume
  flows : index=날짜, column = frgn_eok (외국인 순매수, 억원)      ← foreign_flow.fetch_investor 결과
  buybacks : [{"date": "2026-11-02", "type": "취득결정"|"신탁계약"|"처분결정"|..., "title": ...}, ...]

책의 핵심 도구
  %b        = (종가 - 하단) / (상단 - 하단)      1 초과 = 상단 위, 0 미만 = 하단 아래
  BandWidth = (상단 - 하단) / 중심선              낮을수록 변동성 수축(스퀴즈)
  MFI       = 거래량을 반영한 RSI — 책은 밴드 신호를 '거래량 지표로 확인'하라고 함
  "밴드에 닿는 것 자체는 신호가 아니다" → 아래 세 방법 모두 확인 조건을 붙임

  Method I   스퀴즈 돌파 : BandWidth가 6개월 최저권까지 수축한 뒤 상단 밴드 위로 종가 돌파 + MFI 50 초과
  Method II  추세 추종   : %b > 0.8 이고 MFI > 80 (가격과 거래량이 같이 강할 때)
  Method III W바닥 반전  : 1차 저점은 하단 밴드 밖(%b<0), 2차 저점은 가격이 비슷하거나 더 낮아도
                           밴드 안(%b>0)에서 형성 + MFI가 1차보다 높음 → 두 저점 사이 고점 돌파 시 매수
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class Config:
    n: int = 20                    # 책 기본값 20일
    k: float = 2.0                 # 책 기본값 2 표준편차 (10일이면 1.9, 50일이면 2.1 권장)
    mfi_n: int = 10
    squeeze_lookback: int = 125    # 6개월
    squeeze_tol: float = 1.10      # 최근 20일 BW 최저가 6개월 최저의 110% 이내면 '스퀴즈'
    w_window: int = 40             # W바닥 탐색 구간(영업일)
    w_price_tol: float = 1.03      # 2차 저점이 1차 저점 대비 +3% 이내
    methods: tuple = ("squeeze", "w_bottom")   # 켜 둘 방법 ("trend" 추가 가능). 하나라도 맞으면 볼린저 조건 통과
    buyback_window: int = 10       # 자사주 공시 후 N영업일 이내만 유효
    buyback_types: tuple = ("취득결정", "신탁계약")   # 매수 근거로 인정할 공시
    block_types: tuple = ("처분결정", "신탁해지")     # 이게 더 최근이면 무효
    frgn_days: int = 5
    frgn_min_eok: float = 0.0
    require: tuple = ("buyback", "bollinger", "foreign")  # AND로 묶을 조건 — 빼고 싶으면 여기서 제거


# ── 지표 ──────────────────────────────────────────────
def add_indicators(df: pd.DataFrame, cfg: Config = Config()) -> pd.DataFrame:
    d = df.copy()
    mid = d["close"].rolling(cfg.n).mean()
    sd = d["close"].rolling(cfg.n).std(ddof=0)   # 책은 모집단 표준편차 사용
    d["mid"], d["upper"], d["lower"] = mid, mid + cfg.k * sd, mid - cfg.k * sd
    d["pctb"] = (d["close"] - d["lower"]) / (d["upper"] - d["lower"])
    d["bw"] = (d["upper"] - d["lower"]) / mid
    tp = (d["high"] + d["low"] + d["close"]) / 3
    mf = tp * d["volume"]
    up = mf.where(tp > tp.shift(), 0.0).rolling(cfg.mfi_n).sum()
    dn = mf.where(tp < tp.shift(), 0.0).rolling(cfg.mfi_n).sum()
    d["mfi"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    d.loc[dn == 0, "mfi"] = 100.0
    return d


# ── 책의 세 가지 방법 (i번째 봉 기준, 미래 데이터 안 씀) ──────────────
def method_squeeze(d: pd.DataFrame, i: int, cfg: Config) -> tuple[bool, str]:
    if i < cfg.squeeze_lookback:
        return False, ""
    bw = d["bw"].iloc[: i + 1]
    six_m_low = bw.iloc[-cfg.squeeze_lookback:].min()
    recent_low = bw.iloc[-20:-1].min()
    squeezed = recent_low <= six_m_low * cfg.squeeze_tol
    r, prev = d.iloc[i], d.iloc[i - 1]
    # 처음으로 상단을 넘은 날만 (계속 상단 위에 있는 날은 신호 아님)
    breakout = r["close"] > r["upper"] and prev["close"] <= prev["upper"] and r["mfi"] > 50
    if squeezed and breakout:
        return True, f"스퀴즈 돌파(BW {recent_low:.3f}≈6개월 최저 {six_m_low:.3f}, %b {r['pctb']:.2f}, MFI {r['mfi']:.0f})"
    return False, ""


def method_trend(d: pd.DataFrame, i: int, cfg: Config) -> tuple[bool, str]:
    r = d.iloc[i]
    if r["pctb"] > 0.8 and r["mfi"] > 80:
        return True, f"추세 확인(%b {r['pctb']:.2f}>0.8, MFI {r['mfi']:.0f}>80)"
    return False, ""


def method_w_bottom(d: pd.DataFrame, i: int, cfg: Config) -> tuple[bool, str]:
    lo = max(0, i - cfg.w_window)
    seg = d.iloc[lo: i + 1]
    if len(seg) < 10 or seg["pctb"].isna().any():
        return False, ""
    hist = seg.iloc[:-1]                      # 오늘은 저점 후보에서 제외
    outside = hist[hist["pctb"] < 0]
    if outside.empty:
        return False, ""
    # 1차 저점: 하단 밴드를 뚫은 하락 구간(첫 이탈 ~ 중심선 근처 반등 전)의 최저점
    start = outside.index[0]
    after_start = hist.loc[start:]
    rally = after_start[after_start["pctb"] >= 0.5]
    if rally.empty:
        return False, ""                      # 중간 반등이 아직 없음 → W 아님
    leg = after_start.loc[: rally.index[0]]
    t1 = leg["low"].idxmin()
    p1 = d.at[t1, "low"]
    # 2차 저점: 반등 이후, 1차 저점과 가격이 비슷한(또는 더 낮은) 최저점 — 밴드 안(%b>0)이어야 함
    after = hist.loc[rally.index[0]:]
    if len(after) < 2:
        return False, ""
    t2 = after["low"].idxmin()
    r2 = d.loc[t2]
    if not (r2["low"] <= p1 * cfg.w_price_tol and r2["pctb"] > 0
            and r2["pctb"] > d.at[t1, "pctb"] and r2["mfi"] > d.at[t1, "mfi"]):
        return False, ""
    # 확인: 오늘 종가가 두 저점 사이 최고 종가를 돌파 (2차 저점 이후 첫 돌파만)
    peak = d.loc[t1:t2, "close"].max()
    since_t2 = d.loc[t2: d.index[i]].iloc[1:]   # 오늘까지만 (미래 데이터 금지)
    today = d.iloc[i]
    first_break = today["close"] > peak and (since_t2["close"].iloc[:-1] <= peak).all()
    if first_break:
        return True, (f"W바닥({t1:%m-%d} %b {d.at[t1, 'pctb']:.2f} → {t2:%m-%d} %b {r2['pctb']:.2f}, "
                      f"고점 {peak:,.0f} 돌파)")
    return False, ""


METHODS = {"squeeze": method_squeeze, "trend": method_trend, "w_bottom": method_w_bottom}


def bollinger_check(d: pd.DataFrame, i: int, cfg: Config) -> tuple[bool, str]:
    hits = [msg for m in cfg.methods for ok, msg in [METHODS[m](d, i, cfg)] if ok]
    if hits:
        return True, " / ".join(hits)
    r = d.iloc[i]
    return False, f"볼린저 신호 없음(%b {r['pctb']:.2f}, BW {r['bw']:.3f})"


# ── 자사주 공시 ──────────────────────────────────────
def buyback_check(d: pd.DataFrame, i: int, buybacks: list[dict], cfg: Config) -> tuple[bool, str]:
    today = d.index[i]
    window_start = d.index[max(0, i - cfg.buyback_window + 1)]
    evs = sorted(
        [{**e, "ts": pd.Timestamp(e["date"]).normalize()} for e in buybacks],
        key=lambda e: e["ts"])
    evs = [e for e in evs if e["ts"] <= today]
    if not evs:
        return False, "자사주 공시 없음"
    last_block = max((e["ts"] for e in evs if e["type"] in cfg.block_types), default=None)
    good = [e for e in evs if e["type"] in cfg.buyback_types and e["ts"] >= window_start
            and (last_block is None or e["ts"] > last_block)]
    if good:
        e = good[-1]
        return True, f"자사주 {e['type']} {e['ts']:%m-%d}"
    if last_block is not None and last_block >= window_start:
        return False, f"자사주 처분/해지 공시 {last_block:%m-%d}"
    return False, f"최근 {cfg.buyback_window}영업일 내 자사주 매입 공시 없음"


# ── 외국인 수급 ──────────────────────────────────────
def foreign_check_df(flows: pd.DataFrame | None, today: pd.Timestamp, cfg: Config) -> tuple[bool, str]:
    if flows is None or flows.empty:
        return False, "수급 데이터 없음"
    f = flows.loc[:today, "frgn_eok"].tail(cfg.frgn_days)
    if len(f) < cfg.frgn_days:
        return False, f"수급 {len(f)}일뿐"
    s = round(float(f.sum()), 1)
    return s > cfg.frgn_min_eok, f"외국인 {cfg.frgn_days}일 {s:+}억"


# ── 최종 AND 판정 ────────────────────────────────────
def evaluate(ohlcv: pd.DataFrame, buybacks: list[dict], flows: pd.DataFrame | None = None,
             cfg: Config = Config(), i: int = -1, d: pd.DataFrame | None = None) -> dict:
    """i번째(기본: 마지막) 봉에서 매수 여부. 반환 {"buy", "checks": {이름: (통과, 사유)}, "summary"}"""
    d = add_indicators(ohlcv, cfg) if d is None else d
    i = i % len(d)
    checks = {
        "buyback": buyback_check(d, i, buybacks, cfg),
        "bollinger": bollinger_check(d, i, cfg),
        "foreign": foreign_check_df(flows, d.index[i], cfg),
    }
    used = {k: v for k, v in checks.items() if k in cfg.require}
    buy = all(ok for ok, _ in used.values())
    summary = " · ".join(("✅ " if ok else "❌ ") + msg for ok, msg in used.values())
    return {"date": d.index[i], "buy": buy, "checks": checks, "summary": summary}


def scan(ohlcv: pd.DataFrame, buybacks: list[dict], flows: pd.DataFrame | None = None,
         cfg: Config = Config()) -> pd.DataFrame:
    """전 구간 판정(백테스트·차트용). 매수일과 각 조건 통과 여부를 표로."""
    d = add_indicators(ohlcv, cfg)
    rows = []
    for i in range(cfg.n, len(d)):
        r = evaluate(ohlcv, buybacks, flows, cfg, i, d)
        rows.append({"date": r["date"], "buy": r["buy"],
                     **{f"{k}_ok": v[0] for k, v in r["checks"].items()},
                     "bb_reason": r["checks"]["bollinger"][1]})
    return pd.DataFrame(rows).set_index("date")


def flows_from_rows(rows: list[dict]) -> pd.DataFrame:
    """foreign_flow.fetch_investor() 결과 → flows DataFrame"""
    df = pd.DataFrame(rows)
    df.index = pd.to_datetime(df["date"])
    return df.sort_index()[["frgn_eok"]]
