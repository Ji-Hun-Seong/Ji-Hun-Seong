"""
bb_chart.py — 볼린저 전략 차트 (텔레그램·대시보드용 PNG)

패널: ① 가격 + 볼린저밴드 + 자사주 공시선 + 매수 신호
      ② %b (0·1 기준선, 0.8 추세선)
      ③ BandWidth (6개월 최저권 = 스퀴즈 음영)
      ④ 외국인 순매수(억원)

서버(Ubuntu)에 한글 폰트 필요:  sudo apt install -y fonts-nanum && rm -rf ~/.cache/matplotlib
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib import font_manager
import pandas as pd

from bb_strategy import Config, add_indicators, scan

for _f in ("NanumGothic", "Noto Sans CJK KR", "Noto Sans CJK JP", "AppleGothic", "Malgun Gothic"):
    if any(_f == f.name for f in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = _f
        break
plt.rcParams["axes.unicode_minus"] = False

BG, FG, GRID = "#111827", "#E5E7EB", "#374151"
PRICE, BAND, MID = "#F9FAFB", "#60A5FA", "#9CA3AF"
BUY, BUYBACK, NEG = "#22C55E", "#F59E0B", "#EF4444"


def draw(ohlcv: pd.DataFrame, buybacks: list[dict], flows: pd.DataFrame | None = None,
         title: str = "", path="chart.png", cfg: Config = Config(), last_n: int = 160,
         figsize=(10, 9), font_scale: float = 1.0) -> dict:
    d = add_indicators(ohlcv, cfg)
    sig = scan(ohlcv, buybacks, flows, cfg)
    d = d.join(sig[["buy", "bollinger_ok"]], how="left").tail(last_n)
    d[["buy", "bollinger_ok"]] = d[["buy", "bollinger_ok"]].fillna(False).astype(bool)

    fs = lambda x: x * font_scale
    fig, ax = plt.subplots(4, 1, figsize=figsize, sharex=True,
                           gridspec_kw={"height_ratios": [3.2, 1, 1, 1.1]}, facecolor=BG)
    for a in ax:
        a.set_facecolor(BG)
        a.tick_params(colors=FG, labelsize=fs(8))
        a.grid(color=GRID, lw=0.5, alpha=0.6)
        for s in a.spines.values():
            s.set_color(GRID)

    # ① 가격
    p = ax[0]
    p.fill_between(d.index, d["lower"], d["upper"], color=BAND, alpha=0.10)
    p.plot(d.index, d["upper"], color=BAND, lw=1, label=f"상단 ({cfg.n},{cfg.k})")
    p.plot(d.index, d["lower"], color=BAND, lw=1, label="하단")
    p.plot(d.index, d["mid"], color=MID, lw=0.8, ls="--", label=f"{cfg.n}일 평균")
    p.plot(d.index, d["close"], color=PRICE, lw=1.4, label="종가")
    bb_only = d[d["bollinger_ok"] & ~d["buy"]]
    p.scatter(bb_only.index, bb_only["close"], marker="o", s=40, facecolors="none",
              edgecolors=BAND, lw=1.3, zorder=5, label="볼린저만 충족")
    b = d[d["buy"]]
    p.scatter(b.index, b["low"] * 0.985, marker="^", s=110, color=BUY, zorder=6, label="매수(AND 충족)")
    for e in buybacks:
        t = pd.Timestamp(e["date"])
        if d.index[0] <= t <= d.index[-1]:
            c = NEG if e["type"] in cfg.block_types else BUYBACK
            p.axvline(t, color=c, lw=1, ls=":", alpha=0.9)
            p.text(t, p.get_ylim()[1], f" {e['type']}", color=c, fontsize=fs(8), va="top", rotation=90)
    p.legend(loc="upper left", fontsize=fs(7.5), facecolor=BG, edgecolor=GRID, labelcolor=FG, ncol=2 if figsize[0] < 8 else 3)
    p.set_title(title, color=FG, fontsize=fs(12), loc="left", fontweight="bold")

    # ② %b
    ax[1].plot(d.index, d["pctb"], color=BAND, lw=1)
    for y, c in ((1, NEG), (0, BUY)):
        ax[1].axhline(y, color=c, lw=0.8, alpha=0.7)
    ax[1].axhline(0.8, color=MID, lw=0.6, ls="--")
    ax[1].set_ylabel("%b", color=FG, fontsize=fs(9))

    # ③ BandWidth + 스퀴즈 음영
    bw_low = add_indicators(ohlcv, cfg)["bw"].rolling(cfg.squeeze_lookback).min().reindex(d.index)
    ax[2].plot(d.index, d["bw"], color="#A78BFA", lw=1)
    ax[2].plot(d.index, bw_low, color=MID, lw=0.7, ls="--")
    ax[2].fill_between(d.index, 0, d["bw"].max(), where=d["bw"] <= bw_low * cfg.squeeze_tol,
                       color="#A78BFA", alpha=0.15, step="mid")
    ax[2].set_ylabel("BandWidth", color=FG, fontsize=fs(9))

    # ④ 외국인 순매수
    if flows is not None and not flows.empty:
        f = flows["frgn_eok"].reindex(d.index)
        ax[3].bar(d.index, f, color=[BUY if v >= 0 else NEG for v in f.fillna(0)], width=0.8)
        roll = f.rolling(cfg.frgn_days, min_periods=1).sum()
        ax3b = ax[3].twinx()
        ax3b.plot(d.index, roll, color=BUYBACK, lw=1)
        ax3b.tick_params(colors=BUYBACK, labelsize=fs(7))
        ax3b.set_ylabel(f"{cfg.frgn_days}일 합", color=BUYBACK, fontsize=fs(8))
    ax[3].axhline(0, color=GRID, lw=0.8)
    ax[3].set_ylabel("외국인(억)", color=FG, fontsize=fs(9))
    ax[3].xaxis.set_major_formatter(mdates.DateFormatter("%y-%m"))

    fig.tight_layout()
    fig.savefig(path, dpi=130 if font_scale == 1 else 160, facecolor=BG)
    plt.close(fig)
    return {"path": path, "buy_dates": list(b.index)}
