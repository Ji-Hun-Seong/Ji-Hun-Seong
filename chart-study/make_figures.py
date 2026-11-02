"""차트 공부용 개념 그림 생성 → chart-study/img/*.png
실행: python chart-study/make_figures.py   (한글 폰트 필요: fonts-noto-cjk 또는 fonts-nanum)
그림은 실제 종목이 아니라 개념 설명용 가상 데이터입니다.
"""
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from matplotlib.patches import FancyArrowPatch, Rectangle

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "img")
os.makedirs(OUT, exist_ok=True)
for f in ("NanumGothic", "Noto Sans CJK KR", "Noto Sans CJK JP", "AppleGothic", "Malgun Gothic"):
    if any(f == x.name for x in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = f
        break
plt.rcParams["axes.unicode_minus"] = False

UP, DN, INK, MUT, ACC, BG = "#E5484D", "#3B82F6", "#1F2937", "#9CA3AF", "#F59E0B", "#FFFFFF"
GRN, PUR = "#16A34A", "#8B5CF6"


def fig(w=9, h=4.6, n=1, ratios=None):
    f, ax = plt.subplots(n, 1, figsize=(w, h), facecolor=BG,
                         gridspec_kw={"height_ratios": ratios} if ratios else None, sharex=n > 1)
    axs = np.atleast_1d(ax)
    for a in axs:
        a.set_facecolor(BG)
        for s in ("top", "right"):
            a.spines[s].set_visible(False)
        a.spines["left"].set_color("#D1D5DB"); a.spines["bottom"].set_color("#D1D5DB")
        a.tick_params(colors=MUT, labelsize=8)
    return f, (axs if n > 1 else axs[0])


def save(f, name, title=None):
    if title:
        f.suptitle(title, fontsize=14, fontweight="bold", color=INK, x=0.02, ha="left")
    f.tight_layout()
    f.savefig(os.path.join(OUT, name), dpi=140, facecolor=BG)
    plt.close(f)
    print("✓", name)


def candles(ax, o, h, l, c, x0=0, w=0.6, up=UP, dn=DN):
    for i, (oo, hh, ll, cc) in enumerate(zip(o, h, l, c)):
        col = up if cc >= oo else dn
        x = x0 + i
        ax.plot([x, x], [ll, hh], color=col, lw=1.2, zorder=2)
        ax.add_patch(Rectangle((x - w / 2, min(oo, cc)), w, max(abs(cc - oo), 1e-3 * (hh - ll + 1)),
                               facecolor=col, edgecolor=col, zorder=3))


def series_to_ohlc(close, seed=1, spread=0.012):
    rng = np.random.default_rng(seed)
    c = np.asarray(close, float)
    o = np.r_[c[0], c[:-1]] * (1 + rng.normal(0, spread / 3, len(c)))
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, spread, len(c))))
    l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, spread, len(c))))
    return o, h, l, c


def path(points, n_per=6, noise=0.0, seed=0):
    """꼭짓점 목록 → 부드러운 가격 경로"""
    rng = np.random.default_rng(seed)
    out = []
    for a, b in zip(points[:-1], points[1:]):
        out += list(np.linspace(a, b, n_per, endpoint=False))
    out.append(points[-1])
    out = np.array(out)
    return out * (1 + rng.normal(0, noise, len(out))) if noise else out


def label(ax, x, y, text, color=INK, dy=0, size=10, ha="center", weight="normal"):
    ax.annotate(text, (x, y), xytext=(x, y + dy), ha=ha, va="center", fontsize=size, color=color,
                fontweight=weight, arrowprops=dict(arrowstyle="-", color=color, lw=0.8) if dy else None)


# ── Day 1: 캔들 구조 ───────────────────────────────
def d01():
    f, ax = fig(8, 4.8)
    for x, (o, h, l, c), name, col in [(1, (40, 80, 25, 70), "양봉 (상승)", UP), (4, (70, 85, 22, 35), "음봉 (하락)", DN)]:
        ax.plot([x, x], [l, h], color=col, lw=2.5)
        ax.add_patch(Rectangle((x - 0.45, min(o, c)), 0.9, abs(c - o), color=col))
        ax.text(x, 4, name, ha="center", fontsize=13, fontweight="bold", color=col)
        top, bot = max(o, c), min(o, c)
        for y, t in [(h, "고가"), (l, "저가")]:
            ax.annotate(t, (x, y), xytext=(x + 1.0, y), fontsize=10, va="center", color=INK,
                        arrowprops=dict(arrowstyle="-", color=MUT))
        ax.annotate("종가" if col == UP else "시가", (x + 0.45, top), xytext=(x + 1.0, top - 3), fontsize=10, va="center",
                    arrowprops=dict(arrowstyle="-", color=MUT))
        ax.annotate("시가" if col == UP else "종가", (x + 0.45, bot), xytext=(x + 1.0, bot + 3), fontsize=10, va="center",
                    arrowprops=dict(arrowstyle="-", color=MUT))
        ax.annotate("윗꼬리", (x, (h + top) / 2), xytext=(x - 1.3, (h + top) / 2), fontsize=9, color=MUT, va="center",
                    arrowprops=dict(arrowstyle="-", color=MUT))
        ax.annotate("몸통", (x - 0.45, (top + bot) / 2), xytext=(x - 1.3, (top + bot) / 2), fontsize=9, color=MUT, va="center",
                    arrowprops=dict(arrowstyle="-", color=MUT))
        ax.annotate("아랫꼬리", (x, (l + bot) / 2), xytext=(x - 1.4, (l + bot) / 2), fontsize=9, color=MUT, va="center",
                    arrowprops=dict(arrowstyle="-", color=MUT))
    ax.set_xlim(-0.8, 6); ax.set_ylim(0, 92); ax.set_xticks([]); ax.set_yticks([])
    ax.spines["left"].set_visible(False); ax.spines["bottom"].set_visible(False)
    save(f, "d01_candle.png", "캔들 하나 = 시가·고가·저가·종가 네 가지 가격")


# ── Day 2: 일봉 vs 주봉 ─────────────────────────────
def d02():
    rng = np.random.default_rng(3)
    c = 100 * np.exp(np.cumsum(rng.normal(0.004, 0.022, 60)))
    o, h, l, cc = series_to_ohlc(c, 3, 0.01)
    f, ax = plt.subplots(1, 2, figsize=(10, 4.2), facecolor=BG)
    for a in ax:
        a.set_facecolor(BG); a.tick_params(colors=MUT, labelsize=8)
        for s in ("top", "right"): a.spines[s].set_visible(False)
    candles(ax[0], o, h, l, cc, w=0.7)
    ax[0].set_title("일봉 60개 (약 3달) — 흔들림이 많다", fontsize=11, color=INK, loc="left")
    wk = [(o[i], h[i:i + 5].max(), l[i:i + 5].min(), cc[min(i + 4, 59)]) for i in range(0, 60, 5)]
    candles(ax[1], *zip(*wk), w=0.6)
    ax[1].set_title("같은 기간 주봉 12개 — 방향이 또렷하다", fontsize=11, color=INK, loc="left")
    save(f, "d02_timeframe.png", "타임프레임: 같은 주가, 다른 그림")


# ── Day 3: 단일 캔들 ────────────────────────────────
def d03():
    f, ax = fig(10, 4.4)
    shapes = [("장대양봉", (20, 82, 18, 80)), ("장대음봉", (80, 82, 18, 20)), ("도지", (50, 75, 25, 50.5)),
              ("팽이형", (47, 68, 32, 53)), ("망치형", (62, 70, 20, 68)), ("역망치형", (32, 80, 30, 38)),
              ("유성형", (38, 80, 30, 32))]
    for i, (n, (o, h, l, c)) in enumerate(shapes):
        x = i * 1.5
        col = UP if c >= o else DN
        ax.plot([x, x], [l, h], color=col, lw=2)
        ax.add_patch(Rectangle((x - 0.35, min(o, c)), 0.7, max(abs(c - o), 0.6), color=col))
        ax.text(x, 8, n, ha="center", fontsize=11, color=INK, fontweight="bold")
    ax.text(6.0 * 1.5 / 1.5 * 1.25, 92, "망치형 = 바닥에서 / 같은 모양이 꼭대기면 '교수형'", fontsize=9, color=MUT, ha="center")
    ax.set_xlim(-0.8, 9.8); ax.set_ylim(0, 98); ax.set_xticks([]); ax.set_yticks([])
    ax.spines["left"].set_visible(False); ax.spines["bottom"].set_visible(False)
    save(f, "d03_single.png", "모양 하나에 담긴 매수·매도 싸움")


# ── Day 4: 복합 패턴 ────────────────────────────────
def d04():
    f, axs = plt.subplots(1, 4, figsize=(11, 3.8), facecolor=BG)
    pats = [("상승장악형", [(60, 62, 48, 50), (46, 66, 44, 64)]),
            ("하락장악형", [(50, 62, 48, 60), (64, 66, 44, 46)]),
            ("샛별형", [(70, 72, 48, 50), (46, 49, 40, 45), (48, 70, 47, 68)]),
            ("적삼병", [(40, 52, 38, 50), (49, 62, 47, 60), (59, 72, 57, 70)])]
    for a, (n, cs) in zip(axs, pats):
        a.set_facecolor(BG); a.axis("off")
        # 앞의 추세 맥락
        pre = [(80, 82, 70, 72), (73, 75, 63, 65), (66, 67, 58, 60)] if n != "하락장악형" else [(30, 40, 28, 38), (37, 46, 36, 44), (43, 52, 42, 50)]
        o, h, l, c = zip(*(pre + cs))
        candles(a, o, h, l, c, up="#FCA5A5", dn="#93C5FD", w=0.55)
        o2, h2, l2, c2 = zip(*cs)
        candles(a, o2, h2, l2, c2, x0=len(pre), w=0.55)
        a.set_title(n, fontsize=12, color=INK, fontweight="bold")
        a.set_xlim(-0.8, len(pre) + len(cs) - 0.2)
    save(f, "d04_multi.png", "흐린 캔들 = 앞의 추세 / 진한 캔들 = 패턴")


# ── Day 5: 추세 ─────────────────────────────────────
def d05():
    f, axs = plt.subplots(1, 3, figsize=(11, 3.8), facecolor=BG)
    sets = [("상승추세: 고점↑ 저점↑", [20, 40, 30, 55, 45, 70, 60, 85], UP),
            ("하락추세: 고점↓ 저점↓", [85, 65, 75, 50, 60, 35, 45, 20], DN),
            ("횡보(박스권)", [40, 65, 42, 66, 40, 64, 41, 65], MUT)]
    for a, (t, pts, col) in zip(axs, sets):
        a.set_facecolor(BG); a.set_xticks([]); a.set_yticks([])
        for s in ("top", "right"): a.spines[s].set_visible(False)
        p = path(pts, 6, 0.01, 2)
        a.plot(p, color=col, lw=2)
        xs = np.arange(0, len(p), 6)
        for k, x in enumerate(xs):
            a.scatter(x, pts[k], s=30, color=INK, zorder=5)
            a.text(x, pts[k] + (5 if k % 2 else -7), "고" if (k % 2 == 1) == (col != DN) else "저",
                   ha="center", fontsize=8, color=MUT)
        if col == MUT:
            a.axhline(65.5, color=ACC, ls="--", lw=1); a.axhline(40.5, color=ACC, ls="--", lw=1)
        a.set_title(t, fontsize=11, color=INK, fontweight="bold")
        a.set_ylim(5, 100)
    save(f, "d05_trend.png", "추세는 고점과 저점으로 판단한다")


# ── Day 6: 추세선·채널 ──────────────────────────────
def d06():
    f, ax = fig(9, 4.4)
    lows = [20, 32, 44, 56]
    pts = [20, 38, 32, 50, 44, 62, 56, 74, 60, 52, 46]
    p = path(pts, 6, 0.008, 4)
    o, h, l, c = series_to_ohlc(p, 4, 0.008)
    candles(ax, o, h, l, c, w=0.55)
    x = np.arange(0, 49)
    ax.plot(x, 20 + 12 / 12 * x * 1.0, color=GRN, lw=2, label="상승 추세선 (저점 연결)")
    ax.plot(x, 38 + 12 / 12 * (x - 6) * 1.0, color=GRN, lw=1.2, ls="--", label="채널 상단 (평행선)")
    for i, y in enumerate(lows):
        ax.scatter(i * 12, y, s=60, facecolor="none", edgecolor=GRN, lw=2, zorder=6)
    ax.annotate("추세선 이탈 → 추세 약화", (52, 56), xytext=(39, 30), fontsize=10, color=DN,
                arrowprops=dict(arrowstyle="->", color=DN))
    ax.legend(loc="upper left", fontsize=9, frameon=False)
    ax.set_xticks([])
    save(f, "d06_trendline.png", "저점 2~3개를 이으면 추세선, 평행선을 더하면 채널")


# ── Day 7: 지지·저항 역할 전환 ──────────────────────
def d07():
    f, ax = fig(9.5, 4.4)
    pts = [40, 58, 42, 59, 41, 60, 48, 72, 61, 59, 75, 85]
    p = path(pts, 5, 0.006, 7)
    o, h, l, c = series_to_ohlc(p, 7, 0.008)
    candles(ax, o, h, l, c, w=0.55)
    ax.axhspan(57.5, 60.5, xmin=0, xmax=0.55, color=DN, alpha=0.12)
    ax.axhspan(57.5, 60.5, xmin=0.55, xmax=1, color=GRN, alpha=0.15)
    ax.axhspan(39, 42.5, color=UP, alpha=0.08)
    ax.text(1, 62.5, "저항선 — 세 번 막힘", fontsize=10, color=DN)
    ax.text(1, 36, "지지선", fontsize=10, color=UP)
    ax.annotate("돌파 (거래량↑)", (35, 70), xytext=(24, 78), fontsize=10, color=INK, arrowprops=dict(arrowstyle="->", color=INK))
    ax.annotate("되돌림: 옛 저항이 지지로", (46, 59), xytext=(37, 47), fontsize=10, color=GRN,
                arrowprops=dict(arrowstyle="->", color=GRN))
    ax.set_xticks([])
    save(f, "d07_sr.png", "뚫린 저항은 지지가 된다 (역할 전환)")


# ── Day 8: 가격·거래량 ──────────────────────────────
def d08():
    f, (a, b) = fig(9.5, 5, n=2, ratios=[2.2, 1])
    pts = [50, 48, 51, 49, 50, 70, 80, 82, 83, 84, 78, 70]
    p = path(pts, 5, 0.006, 9)
    o, h, l, c = series_to_ohlc(p, 9, 0.008)
    candles(a, o, h, l, c, w=0.6)
    rng = np.random.default_rng(9)
    v = rng.uniform(0.8, 1.2, len(p))
    v[25:31] *= 3.5; v[35:50] *= 0.5; v[50:] *= 2.2
    b.bar(range(len(p)), v, color=[UP if cc >= oo else DN for oo, cc in zip(o, c)], width=0.6)
    b.axhline(1, color=ACC, ls="--", lw=1); b.text(0, 1.15, "20일 평균", fontsize=8, color=ACC)
    a.text(17, 66, "가격↑ 거래량↑\n건강한 돌파", fontsize=10, color=UP, ha="center")
    a.text(42, 90, "가격↑ 거래량↓\n힘 빠진 상승", fontsize=10, color=MUT, ha="center")
    a.text(51, 64, "가격↓ 거래량↑\n강한 매도", fontsize=10, color=DN, ha="center")
    a.set_ylim(40, 98); b.set_xticks([]); b.set_ylabel("거래량", fontsize=9, color=MUT)
    save(f, "d08_volume.png", "가격과 거래량을 함께 읽기")


# ── Day 9: 이동평균 ─────────────────────────────────
def d09():
    rng = np.random.default_rng(12)
    r = np.r_[rng.normal(-0.004, 0.012, 70), rng.normal(0.006, 0.012, 90), rng.normal(-0.006, 0.012, 60)]
    c = 100 * np.exp(np.cumsum(r))
    f, ax = fig(9.5, 4.4)
    ma = lambda n: np.convolve(c, np.ones(n) / n, "valid")
    x = np.arange(len(c))
    ax.plot(x, c, color=MUT, lw=1, label="종가")
    ax.plot(x[19:], ma(20), color=ACC, lw=2, label="20일선")
    ax.plot(x[59:], ma(60), color=PUR, lw=2, label="60일선")
    m20, m60 = ma(20)[40:], ma(60)
    d = np.sign(m20 - m60)
    for i in np.where(np.diff(d) != 0)[0]:
        xi = i + 60
        gold = d[i + 1] > 0
        ax.scatter(xi, m60[i + 1], s=120, color=GRN if gold else DN, zorder=6, marker="^" if gold else "v")
        ax.text(xi, m60[i + 1] + (-6 if gold else 5), "골든크로스" if gold else "데드크로스",
                ha="center", fontsize=10, color=GRN if gold else DN, fontweight="bold")
    ax.axvspan(115, 155, color=GRN, alpha=0.07); ax.text(135, ax.get_ylim()[0] + 2, "정배열 구간", ha="center", fontsize=9, color=GRN)
    ax.legend(loc="upper left", fontsize=9, frameon=False); ax.set_xticks([])
    save(f, "d09_ma.png", "단기선이 장기선을 뚫는 순간")


# ── Day 10: 반전 패턴 ───────────────────────────────
def d10():
    f, axs = plt.subplots(1, 2, figsize=(11, 4), facecolor=BG)
    hs = path([30, 60, 48, 78, 48, 62, 47, 30], 6, 0.006, 5)
    db = path([75, 40, 60, 41, 62, 80], 7, 0.006, 6)
    for a, p, t in [(axs[0], hs, "헤드앤숄더 (천장)"), (axs[1], db, "이중바닥 W (바닥)")]:
        a.set_facecolor(BG); a.set_xticks([]); a.set_yticks([])
        for s in ("top", "right"): a.spines[s].set_visible(False)
        a.plot(p, color=INK, lw=2); a.set_title(t, fontsize=12, color=INK, fontweight="bold")
    axs[0].axhline(48, color=DN, ls="--", lw=1.5); axs[0].text(1, 50, "넥라인", color=DN, fontsize=10)
    for x, y, n in [(6, 60, "왼어깨"), (18, 78, "머리"), (30, 62, "오른어깨")]:
        axs[0].text(x, y + 3, n, ha="center", fontsize=10, color=INK)
    axs[0].annotate("", (43, 30), (43, 48), arrowprops=dict(arrowstyle="->", color=DN, lw=1.5))
    axs[0].text(44, 38, "목표 ≈\n머리~넥라인 높이", fontsize=9, color=DN)
    axs[1].axhline(60.5, color=GRN, ls="--", lw=1.5); axs[1].text(1, 62.5, "넥라인 (중간 고점)", color=GRN, fontsize=10)
    axs[1].text(7, 36, "1차 저점", ha="center", fontsize=10); axs[1].text(21, 37, "2차 저점", ha="center", fontsize=10)
    axs[1].annotate("넥라인 돌파 = 패턴 완성", (31, 64), xytext=(17, 76), fontsize=10, color=GRN,
                    arrowprops=dict(arrowstyle="->", color=GRN))
    save(f, "d10_reversal.png", "넥라인이 깨져야 패턴이 완성된다")


# ── Day 11: 지속 패턴 ───────────────────────────────
def d11():
    f, axs = plt.subplots(1, 2, figsize=(11, 4), facecolor=BG)
    tri = path([40, 70, 46, 64, 51, 60, 54, 57, 75], 5, 0.004, 1)
    flag = path([30, 70, 64, 67, 61, 64, 58, 85], 5, 0.004, 2)
    for a, p, t in [(axs[0], tri, "대칭 삼각형 (삼각수렴)"), (axs[1], flag, "깃발형")]:
        a.set_facecolor(BG); a.set_xticks([]); a.set_yticks([])
        for s in ("top", "right"): a.spines[s].set_visible(False)
        a.plot(p, color=INK, lw=2); a.set_title(t, fontsize=12, color=INK, fontweight="bold")
    axs[0].plot([5, 35], [70, 57.5], color=DN, ls="--"); axs[0].plot([10, 35], [46, 55.5], color=UP, ls="--")
    axs[0].annotate("에너지 압축 후 돌파", (37, 62), xytext=(18, 74), fontsize=10, color=INK, arrowprops=dict(arrowstyle="->"))
    axs[1].plot([5, 30], [70, 61], color=MUT, ls="--"); axs[1].plot([10, 30], [64, 58], color=MUT, ls="--")
    axs[1].text(1, 50, "깃대\n(급등)", fontsize=10, color=UP); axs[1].text(16, 72, "깃발 (짧은 휴식)", fontsize=10, color=MUT)
    save(f, "d11_continuation.png", "쉬었다가 가던 방향으로")


# ── Day 12: RSI 다이버전스 ──────────────────────────
def d12():
    f, (a, b) = fig(9.5, 5, n=2, ratios=[1.6, 1])
    p = path([80, 60, 68, 50, 58, 46, 52, 66], 7, 0.004, 8)
    a.plot(p, color=INK, lw=1.8)
    a.plot([21, 35], [50, 46], color=DN, lw=2); a.text(28, 42, "가격: 저점 더 낮아짐", ha="center", fontsize=10, color=DN)
    rsi = path([60, 28, 45, 33, 48, 40, 50, 62], 7, 0, 0)
    b.plot(rsi, color=PUR, lw=1.8); b.axhline(70, color=UP, ls="--", lw=1); b.axhline(30, color=GRN, ls="--", lw=1)
    b.text(0.5, 72, "70 과매수", fontsize=8, color=UP); b.text(0.5, 24, "30 과매도", fontsize=8, color=GRN)
    b.plot([21, 35], [33, 40], color=GRN, lw=2); b.text(28, 18, "RSI: 저점 높아짐 → 강세 다이버전스", ha="center", fontsize=10, color=GRN)
    b.set_ylim(10, 90); b.set_ylabel("RSI", fontsize=9, color=MUT); b.set_xticks([])
    save(f, "d12_rsi.png", "가격과 지표가 엇갈리면 경고 신호")


# ── Day 13: MACD ────────────────────────────────────
def d13():
    rng = np.random.default_rng(21)
    c = 100 * np.exp(np.cumsum(np.r_[rng.normal(-0.004, 0.01, 50), rng.normal(0.006, 0.01, 60), rng.normal(-0.003, 0.01, 40)]))
    ema = lambda s, n: np.array([s[:i + 1][-1] if i == 0 else 0 for i in range(len(s))])
    def e(s, n):
        k, out = 2 / (n + 1), [s[0]]
        for v in s[1:]:
            out.append(out[-1] + k * (v - out[-1]))
        return np.array(out)
    macd = e(c, 12) - e(c, 26); sig = e(macd, 9); hist = macd - sig
    f, (a, b) = fig(9.5, 5, n=2, ratios=[1.4, 1])
    a.plot(c, color=INK, lw=1.5); a.set_ylabel("가격", fontsize=9, color=MUT)
    b.bar(range(len(c)), hist, color=[UP if v >= 0 else DN for v in hist], width=0.8, alpha=0.6, label="히스토그램")
    b.plot(macd, color=ACC, lw=1.6, label="MACD (12-26)"); b.plot(sig, color=PUR, lw=1.3, label="시그널 (9)")
    b.axhline(0, color=MUT, lw=0.8); b.legend(fontsize=8, frameon=False, loc="upper left", ncol=3)
    save(f, "d13_macd.png", "MACD: 시그널선 교차와 히스토그램")


# ── Day 14: 볼린저 밴드 ─────────────────────────────
def d14():
    rng = np.random.default_rng(5)
    r = np.r_[rng.normal(0, 0.018, 60), rng.normal(0, 0.004, 45), np.full(6, 0.02) + rng.normal(0, 0.004, 6), rng.normal(0.006, 0.01, 30)]
    c = 100 * np.exp(np.cumsum(r))
    n = 20
    mid = np.array([c[max(0, i - n + 1):i + 1].mean() for i in range(len(c))])
    sd = np.array([c[max(0, i - n + 1):i + 1].std() for i in range(len(c))])
    up, lo = mid + 2 * sd, mid - 2 * sd
    f, (a, b) = fig(9.5, 5.4, n=2, ratios=[2, 1])
    x = np.arange(len(c))[n:]
    a.fill_between(x, lo[n:], up[n:], color=DN, alpha=0.08)
    a.plot(x, up[n:], color=DN, lw=1.2, label="상단 (평균+2σ)"); a.plot(x, lo[n:], color=DN, lw=1.2, label="하단 (평균−2σ)")
    a.plot(x, mid[n:], color=MUT, lw=1, ls="--", label="20일 평균"); a.plot(x, c[n:], color=INK, lw=1.6, label="종가")
    a.axvspan(70, 105, color=PUR, alpha=0.08); a.text(87, a.get_ylim()[0] if False else min(lo[n:]) + 1, "스퀴즈\n(폭풍 전 고요)", ha="center", fontsize=10, color=PUR)
    bo = 105 + int(np.argmax(c[105:111] > up[105:111]))
    a.annotate("Method I: 스퀴즈 후 상단 돌파", (bo, c[bo]), xytext=(bo - 40, c[bo] + 6), fontsize=10, color=GRN,
               arrowprops=dict(arrowstyle="->", color=GRN))
    a.annotate("밴드 타기 — 상단 터치는\n매도 신호가 아니다", (125, up[125]), xytext=(60, up[125] + 4), fontsize=9, color=UP,
               arrowprops=dict(arrowstyle="->", color=UP))
    a.legend(fontsize=8, frameon=False, loc="upper left", ncol=2)
    bw = (up - lo) / mid
    b.plot(x, bw[n:], color=PUR, lw=1.5); b.set_ylabel("밴드폭", fontsize=9, color=MUT); b.set_xticks([])
    save(f, "d14_bb.png", "볼린저 밴드: 수축(스퀴즈) 뒤에 확장이 온다")


# ── Day 15: 피보나치 ────────────────────────────────
def d15():
    f, ax = fig(9.5, 4.4)
    p = path([40, 100, 76, 82, 64, 90, 108], 8, 0.004, 3)
    ax.plot(p, color=INK, lw=1.8)
    lo, hi = 40, 100
    for r, col in [(0.236, MUT), (0.382, ACC), (0.5, PUR), (0.618, GRN), (0.786, MUT)]:
        y = hi - (hi - lo) * r
        ax.axhline(y, color=col, ls="--", lw=1)
        ax.text(len(p) - 0.5, y + 0.8, f"{r * 100:.1f}%", fontsize=9, color=col, ha="right")
    ax.text(8, 102, "고점", ha="center", fontsize=10); ax.text(0, 36, "저점", fontsize=10)
    ax.annotate("61.8% 근처에서 지지 → 재상승", (32, 64), xytext=(36, 50), fontsize=10, color=GRN,
                arrowprops=dict(arrowstyle="->", color=GRN))
    ax.set_xticks([])
    save(f, "d15_fib.png", "피보나치 되돌림: 상승폭의 몇 %를 돌려주나")


# ── Day 16: 수급 ────────────────────────────────────
def d16():
    rng = np.random.default_rng(16)
    fl = np.r_[rng.normal(-3, 4, 25), rng.normal(5, 3, 25), rng.normal(-1, 4, 15)]
    c = 100 * np.exp(np.cumsum(0.004 * fl / 4 + rng.normal(0, 0.008, len(fl))))
    f, (a, b) = fig(9.5, 5, n=2, ratios=[1.5, 1])
    a.plot(c, color=INK, lw=1.6); a.set_ylabel("주가", fontsize=9, color=MUT)
    a.axvline(30, color=ACC, ls=":", lw=1.5); a.text(30.5, a.get_ylim()[1] if False else max(c), " 자사주 매입 공시", fontsize=9, color=ACC, va="top")
    b.bar(range(len(fl)), fl, color=[GRN if v >= 0 else UP for v in fl], width=0.8)
    roll = np.convolve(fl, np.ones(5), "full")[:len(fl)]
    b2 = b.twinx(); b2.plot(roll, color=ACC, lw=1.4); b2.tick_params(colors=ACC, labelsize=8)
    b2.set_ylabel("5일 합", color=ACC, fontsize=9); b2.spines["top"].set_visible(False)
    b.axhline(0, color=MUT, lw=0.8); b.set_ylabel("외국인 순매수(억)", fontsize=9, color=MUT); b.set_xticks([])
    save(f, "d16_flow.png", "외국인이 꾸준히 사는 구간에서 추세가 이어진다")


# ── Day 17: 손익비 ──────────────────────────────────
def d17():
    f, ax = fig(9.5, 4.4)
    p = path([70, 52, 60, 54, 66, 82, 92], 7, 0.004, 17)
    o, h, l, c = series_to_ohlc(p, 17, 0.006)
    candles(ax, o, h, l, c, w=0.55)
    entry, stop, target = 56, 50, 68
    ax.axhspan(stop, entry, xmin=0.42, xmax=0.95, color=UP, alpha=0.15)
    ax.axhspan(entry, target, xmin=0.42, xmax=0.95, color=GRN, alpha=0.15)
    for y, t, col in [(entry, "진입 56", INK), (stop, "손절 50  (−6)", UP), (target, "목표 68  (+12)", GRN)]:
        ax.axhline(y, xmin=0.42, xmax=0.95, color=col, lw=1.4)
        ax.text(len(p) * 0.96, y, t, fontsize=10, color=col, va="center")
    ax.text(len(p) * 0.68, 59, "손익비 2 : 1", fontsize=13, color=INK, fontweight="bold", ha="center")
    ax.text(1, 47, "손절은 지지선 바로 아래", fontsize=9, color=MUT)
    ax.set_xlim(-1, len(p) * 1.18); ax.set_xticks([])
    save(f, "d17_risk.png", "사기 전에 정한다: 진입·손절·목표")


# ── Day 18: 감정 사이클 ─────────────────────────────
def d18():
    f, ax = fig(9.5, 4.4)
    x = np.linspace(0, 10, 300)
    y = np.sin(x * 0.75 - 1.2) * 40 + 50
    ax.plot(x, y, color=INK, lw=2)
    marks = [(0.4, "의심"), (2.0, "희망"), (2.9, "확신"), (3.6, "흥분·FOMO\n(여기서 산다)"), (4.6, "불안"),
             (5.6, "부정"), (6.6, "공포"), (7.6, "투매\n(여기서 판다)"), (8.8, "다시 희망")]
    for xi, t in marks:
        yi = np.sin(xi * 0.75 - 1.2) * 40 + 50
        bad = "FOMO" in t or "투매" in t
        ax.scatter(xi, yi, s=40, color=UP if bad else MUT, zorder=5)
        ax.text(xi, yi + (7 if yi > 50 else -12), t, ha="center", fontsize=9.5, color=UP if bad else INK,
                fontweight="bold" if bad else "normal")
    ax.set_ylim(-5, 108); ax.set_xticks([]); ax.set_yticks([])
    save(f, "d18_psych.png", "감정은 꼭지에서 사고 바닥에서 팔게 만든다")


if __name__ == "__main__":
    for fn in (d01, d02, d03, d04, d05, d06, d07, d08, d09, d10, d11, d12, d13, d14, d15, d16, d17, d18):
        fn()
