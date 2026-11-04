"""
heroes_core.py — 가치 5인·성장 5인 대가의 '원전 기준'을 숫자로 옮긴 채점 엔진 (heroes.score 가 이걸 씀)
  2026-11-05 3차 개편: 그린블랫·오닐 → 멍거·클라만(가치), 드러켄밀러·템플턴(성장)으로 교체, 로 프라이스 '성장의 계절' 추가

객관화 원칙
  1) 기준선 = 책·주주서한에 나온 숫자 그대로 (📖). 원전에 숫자가 없으면 공개된 보조선(⚖️)을 쓰고 화면에 그렇게 표시
  2) 계단식 점수 X → 0점 선과 만점 선 사이를 직선으로(연속 점수). 0점 선은 원전에 있으면 그 값,
     없으면 '기준선에서 50% 벗어난 곳'으로 통일
  3) 한 대가 안의 항목은 모두 같은 비중 — 저자가 목록으로 나열한 그대로(누가 더 중요한지 내가 정하지 않음)
  4) 데이터가 없으면 0.5(반만 인정), 해당 없는 기준(금융업 유동비율 등)은 계산에서 뺌
  5) 같은 입력이면 언제나 같은 점수 — 사람 판단(경영진·해자 등)은 점수에 넣지 않고 '직접 확인' 목록으로

출처 약어
  ─ 가치주 5인 ─
  버핏      버크셔 주주서한 1977·1979·1983·1984·1986·1989·2007 · 주주총회 문답 · 2010 FCIC 인터뷰(가격 결정력)
  그레이엄  『현명한 투자자』(II) 14장 방어적 투자자 · 15장 기업형 투자자/넷넷 · 『증권분석』(SA) 수익력·투기 한계
  멍거      『가난한 찰리의 연감』 · 1994 USC '세속적 지혜' 강연(ROE 6% vs 18%) · 1995 '인간 오판의 심리학' · 웨스코/데일리저널 주총
  애크먼    퍼싱스퀘어 투자 원칙(연차 서한·IR 자료)
  클라만    『안전마진』(1991) — 보수적 가치 범위·하방 우선·소외 종목·촉매 · 바우포스트 연례 서한
  ─ 성장주 5인 ─
  린치      『전설로 떠나는 월가의 영웅』(OU) 7·8·13·15장 · 『이기는 투자』(BS) 25가지 황금률·S&L 점검표 · 『Learn to Earn』(LE)
  피셔      『위대한 기업에 투자하라』(CS) 15가지 · 『보수적인 투자자는 마음이 편하다』(CI) 4가지 차원
  드러켄밀러 『새로운 시장의 마법사들』(1992) 인터뷰 · 2015 로스트트리 강연 · Sohn 컨퍼런스 · 2023 노르웨이 국부펀드 인터뷰
  템플턴    16계명(1993) · 『템플턴 플랜』 · 『존 템플턴의 가치투자 전략』(2008) — 미래 이익 대비 가격·5년 평균 이익·최대 비관
  로 프라이스  1939 배런스 기고 'Picking Growth Stocks' · 1973 'The New Era for Investors'
"""
from __future__ import annotations

import math
import statistics as stx

BOND = {"kr": 3.0, "us": 4.2}     # 10년 국채 금리(%, 대략) — 버핏 '이익수익률을 국채와 비교'용. 크게 바뀌면 고칠 것


def ok_(v):
    return v is not None and not (isinstance(v, float) and (math.isnan(v) or math.isinf(v)))


def ramp(v, zero, full):
    """v 가 zero 면 0, full 이면 1, 사이는 직선 (방향은 zero/full 순서로 정해짐)"""
    if not ok_(v):
        return None
    if full == zero:
        return 1.0 if v >= full else 0.0
    return max(0.0, min(1.0, (v - zero) / (full - zero)))


def C(src, text, s, line="", orig=True, na=False, bonus=False):
    """체크 한 줄. s = 0~1 (None = 데이터 없음). orig=True 면 기준선이 원전 숫자(📖), False 면 보조선(⚖️)"""
    if na:
        return {"pts": 0, "max": 1, "ok": None, "na": True, "text": text, "src": src, "line": line, "orig": orig}
    if bonus:
        return {"pts": 0, "max": 0, "ok": True, "bonus": True, "text": text, "src": src, "line": line, "orig": orig}
    ok = None if s is None else True if s >= 0.95 else False if s <= 0.05 else "part"
    return {"pts": round(s, 2) if s is not None else 0, "max": 1, "ok": ok, "text": text, "src": src, "line": line, "orig": orig}


def cagr(a, b, n):
    if not (ok_(a) and ok_(b)) or a <= 0 or b <= 0 or n <= 0:
        return None
    return (b / a) ** (1 / n) - 1


def last(x, n):
    return [v for v in (x or []) if v is not None][-n:]


def lastv(x):
    v = last(x, 1)
    return v[0] if v else None


def yr_vals(by: dict, k: str, n: int = 10):
    """연도 → 값 사전에서 최근 n년 (오래된 → 최신), 값 없는 해는 빠짐"""
    m = by.get(k) or {}
    ys = sorted(m)[-n:]
    return [(y, m[y]) for y in ys if m[y] is not None]


def f1(v, d=1):
    return "-" if v is None else f"{v:,.{d}f}"


# ════════════════════════════════════════════════════════════════
def graham(F):
    g, by, fin = [], F["by"], F["fin_co"]
    mc, per, pbr = F["mcap_eok"], F["per"], F["pbr"]
    II14, II15, SA = "『현명한 투자자』14장", "『현명한 투자자』15장", "『증권분석』"
    # ① 충분한 규모 — 원전(1973): 연 매출 1억 달러 이상 → 물가 반영 약 7.7배 ≈ 1조원
    rev = lastv(F["rev"])
    if not F["us"] and rev is not None:
        g.append(C(II14, f"① 충분한 규모: 연 매출 {rev / 10000:.2f}조원", ramp(rev, 2500, 10000),
                   "📖 매출 1억 달러(1973) ≈ 지금 1조원 이상 · 0.25조↓ 0점"))
    elif mc:
        g.append(C(II14, f"① 충분한 규모: 시가총액 {mc / 10000:.1f}조원 (해외는 매출 대신 시총)", ramp(mc, 5000, 20000),
                   "⚖️ 매출 대신 시총 2조원 이상", orig=False))
    else:
        g.append(C(II14, "① 규모: 데이터 없음", None))
    # ② 유동비율 200% · ③ 장기부채 ≤ 순유동자산
    cr = lastv(F["cr"])
    if fin:
        g.append(C(II14, "② 유동비율: 금융업 — 그레이엄도 이 기준은 산업 회사에만 적용", None, na=True))
        g.append(C(II14, "③ 장기부채: 금융업 — 제외", None, na=True))
    else:
        g.append(C(II14, f"② 튼튼한 재무: 유동비율 {f1(cr, 0)}%", ramp(cr, 100, 200), "📖 200%↑ 만점 · 100%↓ 0점(유동부채도 못 갚음)")
                 if cr is not None else C(II14, "② 유동비율: 데이터 없음", None))
        ca, cl, ncl = lastv(F["ca"]), lastv(F["cl"]), lastv(F["ncl"])
        if None not in (ca, cl, ncl):
            wc = ca - cl
            r = ncl / wc if wc > 0 else None
            g.append(C(II14, f"③ 장기부채 ≤ 순유동자산: 비유동부채 {f1(ncl, 0)}억 ÷ (유동자산−유동부채) {f1(wc, 0)}억 = "
                       + (f"{r:.2f}배" if r is not None else "순유동자산 마이너스"),
                       0.0 if r is None else ramp(r, 1.5, 1.0), "📖 1배↓ 만점 · 1.5배↑ 0점"))
        else:
            g.append(C(II14, "③ 장기부채 vs 순유동자산: 데이터 없음", None))
    # ④ 10년 무적자 — 모르는 해는 반만 인정
    ni = yr_vals(by, "ni", 10)
    if ni:
        pos = sum(1 for _, v in ni if v > 0)
        loss = len(ni) - pos
        s = (pos + 0.5 * (10 - len(ni))) / 10 if not loss else max(0.0, pos / 10 - 0.3 * loss)
        g.append(C(II14, f"④ 이익 안정: 최근 {len(ni)}년 " + ("모두 흑자" if not loss else f"중 적자 {loss}번"), s,
                   "📖 10년 동안 적자 0번 (확인 못 한 해는 반만 인정)"))
    else:
        g.append(C(II14, "④ 이익 안정: 데이터 없음", None))
    # ⑤ 20년 연속 배당
    dp = yr_vals(by, "dps", 25)
    if dp:
        run = 0
        for _, v in reversed(dp):
            if v and v > 0:
                run += 1
            else:
                break
        unknown = max(0, 20 - len(dp)) if run == len(dp) else 0     # 데이터 시작까지 끊김이 없었으면 그 이전은 모름
        g.append(C(II14, f"⑤ 배당 이력: {run}년 연속 배당" + (f" (그 이전 {unknown}년은 데이터 없음)" if unknown else ""),
                   min(1.0, (run + 0.5 * unknown) / 20), "📖 20년 연속 배당"))
    elif F["dy"] is not None:
        g.append(C(II14, f"⑤ 배당 이력: 현재 배당 {'있음' if F['dy'] > 0 else '없음'} (연속 연수 모름)", None if F["dy"] > 0 else 0.0, "📖 20년 연속 배당"))
    else:
        g.append(C(II14, "⑤ 배당 이력: 데이터 없음", None))
    # ⑥ 10년간 EPS 1/3 성장 (앞뒤 3년 평균)
    e = [v for _, v in yr_vals(by, "eps", 10)]
    if len(e) >= 6:
        a0, a1 = sum(e[:3]) / 3, sum(e[-3:]) / 3
        gr = a1 / a0 - 1 if a0 > 0 else None
        g.append(C(II14, f"⑥ 이익 성장: 3년 평균 EPS {f1(a0, 0)} → {f1(a1, 0)} ({'계산 불가' if gr is None else f'{gr * 100:+.0f}%'}, {len(e)}년)",
                   0.0 if gr is None else ramp(gr, 0, 1 / 3), "📖 10년 동안 +33%↑ · 0%↓ 0점"))
    else:
        g.append(C(II14, "⑥ 이익 성장: EPS 6년치 미만", None))
    # ⑦ 주가 ≤ 3년 평균 EPS × 15
    close = F["close"]
    e3 = e[-3:]
    if close and len(e3) == 3 and sum(e3) > 0:
        pe3 = close / (sum(e3) / 3)
        g.append(C(II14, f"⑦ 적당한 PER: 주가 ÷ 3년 평균 EPS = {pe3:.1f}배", ramp(pe3, 20, 15),
                   "📖 15배↓ 만점 · 20배↑ 0점(『증권분석』의 투기 한계)"))
    elif per:
        g.append(C(II14, f"⑦ 적당한 PER: 현재 PER {per:.1f}배 (3년 평균 EPS 없음)", ramp(per, 20, 15), "📖 15배↓ · 20배↑ 0점"))
    else:
        g.append(C(II14, "⑦ PER: 적자이거나 데이터 없음", 0.0 if pbr else None))
    # ⑧ PBR 1.5 또는 PER×PBR 22.5
    if pbr:
        s = ramp(pbr, 2.25, 1.5)
        txt = f"⑧ 적당한 PBR: {pbr:.2f}배"
        if per and per > 0:
            s = max(s, ramp(per * pbr, 33.75, 22.5))
            txt += f" · PER×PBR {per * pbr:.1f}"
        g.append(C(II14, txt, s, "📖 PBR 1.5↓ 또는 PER×PBR 22.5↓ · 50% 넘으면 0점"))
    else:
        g.append(C(II14, "⑧ PBR: 데이터 없음", None))
    # ⑨ 『증권분석』 수익력: 5~10년 평균 이익 기준 가격
    e10 = e[-10:]
    if close and len(e10) >= 5 and sum(e10) > 0:
        pe10 = close / (sum(e10) / len(e10))
        g.append(C(SA, f"⑨ 수익력 대비 가격: 주가 ÷ {len(e10)}년 평균 EPS = {pe10:.1f}배", ramp(pe10, 30, 20),
                   "📖 평균 이익의 약 20배가 투자로 낼 수 있는 상한 · 30배↑ 0점"))
    else:
        g.append(C(SA, "⑨ 수익력(5~10년 평균 이익): 데이터 부족", None))
    # 배지 — 점수엔 안 들어감
    ca, li = lastv(F["ca"]), lastv(F["liab"])
    if mc and ca is not None and li is not None and not fin and ca - li > 0 and mc < (ca - li) * 2 / 3:
        g.append(C(II15, f"💎 넷넷: 시총 {f1(mc, 0)}억 < (유동자산−총부채) {f1(ca - li, 0)}억의 2/3 — 그레이엄의 '헐값' 종목", None, bonus=True))
    n5 = [v for _, v in yr_vals(by, "ni", 5)]
    ent = (not fin and cr is not None and cr >= 150 and len(n5) >= 5 and all(v > 0 for v in n5) and (F["dy"] or 0) > 0
           and len(e) >= 2 and e[-1] > e[-2] and pbr is not None and pbr <= 1.2)
    if ent:
        g.append(C(II15, "🏅 기업형 투자자 5기준 통과 (유동비율 150%↑·5년 흑자·배당·이익 증가·PBR 1.2↓)", None, bonus=True))
    eps_l = lastv(F["eps"])
    if close and pbr and pbr > 0 and eps_l and eps_l > 0:
        gnum = math.sqrt(22.5 * eps_l * (close / pbr))
        g.append(C(II14, f"🔢 그레이엄 넘버 √(22.5×EPS×BPS) = {gnum:,.0f} → 현재가는 그 {close / gnum * 100:.0f}%", None, bonus=True))
    fail = bool(ni and any(v <= 0 for _, v in ni)) or bool(F["dr"] and not fin and F["dr"][-1] >= 200)
    todo = ["가격이 가치보다 충분히 쌀 때만 사는가 — '미스터 마켓'의 기분에 휩쓸리지 않기 (II 8장·20장 안전마진)",
            "방어적 투자자라면 10~30종목으로 나눴는가 (II 5장)",
            "순이익이 일회성 이익으로 부풀려지지 않았는가 (II 12장 '주당순이익에 대한 고찰')"]
    return g, todo, fail


# ════════════════════════════════════════════════════════════════
def buffett(F):
    b, by, fin = [], F["by"], F["fin_co"]
    per, mc = F["per"], F["mcap_eok"]
    ni = yr_vals(by, "ni", 10)
    # ① 꾸준한 수익력 (1984 인수 기준: 'demonstrated consistent earning power… turnaround 는 관심 없음')
    if len(ni) >= 3:
        good, prev = 0, None
        for _, v in ni:
            if v > 0 and (prev is None or prev <= 0 or v >= prev * 0.5):
                good += 1
            prev = v
        b.append(C("1984 서한·인수 기준", f"① 꾸준한 수익력: {len(ni)}년 중 {good}년이 흑자이면서 이익 반토막 없음",
                   (good + 0.5 * (10 - len(ni))) / 10, "📖 10년 내내 흑자·급감 없음 (턴어라운드 X)"))
    else:
        b.append(C("1984 서한·인수 기준", "① 꾸준한 수익력: 3년치 미만", None))
    # ② ③ ROE (1979 서한: 경영 성과의 1차 척도는 EPS가 아니라 자기자본이익률 / 장기 목표 15%)
    rr = [v for _, v in yr_vals(by, "roe", 10)] or last(F["roe"], 10)
    if rr:
        avg, mn = sum(rr) / len(rr), min(rr)
        b.append(C("1979 서한", f"② 높은 ROE: {len(rr)}년 평균 {avg:.1f}%", ramp(avg, 7.5, 15), "📖 15%↑ (버크셔 목표 수익률) · 7.5%↓ 0점"))
        b.append(C("1979·1987 서한", f"③ 꾸준한 ROE: 가장 나빴던 해 {mn:.1f}%", ramp(mn, 7.5, 15) if len(rr) >= 3 else None,
                   "📖 나쁜 해에도 15%↑ · 7.5%↓ 0점"))
    else:
        b += [C("1979 서한", "② ROE: 데이터 없음", None), C("1979 서한", "③ ROE 꾸준함: 데이터 없음", None)]
    # ④ 빚 없이 (1984: 'good returns on equity while employing little or no debt')
    nc, nil = lastv(F["netcash"]), lastv(F["ni"])
    if fin:
        b.append(C("1984 서한·인수 기준", "④ 빚: 금융업 — 제외", None, na=True))
    elif nc is not None and nil:
        yrs = (-nc / nil) if nc < 0 and nil > 0 else (0 if nc >= 0 else 99)
        b.append(C("1984 서한·인수 기준", "④ 빚 없이 번다: " + ("순현금" if nc >= 0 else f"순차입 = 순이익의 {yrs:.1f}년치"),
                   ramp(yrs, 3, 0), "📖 빚이 거의 없을 것 → ⚖️ 순현금 만점 · 순차입이 순이익 3년치↑ 0점", orig=False))
    elif F["dr"]:
        b.append(C("1984 서한·인수 기준", f"④ 빚: 부채비율 {F['dr'][-1]:.0f}%", ramp(F["dr"][-1], 150, 50), "⚖️ 50%↓ 만점 · 150%↑ 0점", orig=False))
    else:
        b.append(C("1984 서한·인수 기준", "④ 빚: 데이터 없음", None))
    # ⑤ 주주 이익 (1986 서한 부록: 순이익 + 감가상각 − 유지 설비투자 ≈ FCF)
    fc, nq = last(F["fcf"], 5), last(F["ni"], 5)
    if len(fc) >= 3 and len(nq) >= len(fc) and sum(nq[-len(fc):]) > 0:
        conv = sum(fc) / sum(nq[-len(fc):])
        b.append(C("1986 서한", f"⑤ 주주 이익: {len(fc)}년 FCF ÷ 순이익 = {conv * 100:.0f}%", ramp(conv, 0.5, 1.0),
                   "📖 회계 이익보다 '주주 이익'(현금) → ⚖️ 100%↑ 만점 · 50%↓ 0점", orig=False))
    else:
        b.append(C("1986 서한", "⑤ 주주 이익(FCF): 데이터 없음", None))
    # ⑥ 자본이 적게 드는 사업 (2007 서한: 위대한/좋은/끔찍한 사업 — 성장에 돈이 덜 드는 회사)
    oc, cx = last(F["ocf"], 5), last(F["capex"], 5)
    if len(oc) >= 3 and len(cx) >= 3 and sum(oc[-3:]) > 0:
        ci = sum(cx[-3:]) / sum(oc[-3:])
        b.append(C("2007 서한", f"⑥ 돈 덜 드는 사업: 설비투자 ÷ 영업현금흐름 = {ci * 100:.0f}% (3년)", ramp(ci, 0.9, 0.4),
                   "⚖️ 40%↓ 만점 · 90%↑ 0점 (번 돈을 다시 설비에 넣어야 하면 '좋은' 사업, 아니면 '위대한' 사업)", orig=False))
    else:
        b.append(C("2007 서한", "⑥ 설비투자 부담: 데이터 없음", None))
    # ⑦ 1달러 테스트 (1983 서한: 남긴 1원이 5년에 걸쳐 시장가치 1원 이상이 되었나)
    px, sh, nio, dps = by.get("yclose") or {}, by.get("shares") or {}, by.get("nio") or {}, by.get("dps") or {}
    ys = sorted(y for y in nio if nio[y] is not None)
    t = None
    if len(ys) >= 6 and mc:
        y0 = ys[-6]
        if px.get(y0) and sh.get(y0):
            mc0 = px[y0] * sh[y0] / 1e8
            ret = sum(nio[y] - (dps.get(y) or 0) * (sh.get(y) or 0) / 1e8 for y in ys[-5:])
            if ret > 0:
                t = (mc - mc0) / ret
                b.append(C("1983 서한", f"⑦ 1달러 테스트: 5년간 남긴 이익 {f1(ret, 0)}억 → 시가총액 {f1(mc - mc0, 0):}억 변화 = {t:.2f}원/1원",
                           ramp(t, 0, 1), "📖 남긴 1원당 시장가치 1원↑ (5년 단위)"))
    if t is None:
        b.append(C("1983 서한", "⑦ 1달러 테스트: 5년 전 주가·주식 수 데이터 없음", None))
    # ⑧ 가격 — 이익수익률 vs 국채 (주총 문답 · 1989 '훌륭한 회사를 적당한 가격에')
    bond = BOND["us" if F["us"] else "kr"]
    if per and per > 0:
        ey = 100 / per
        b.append(C("주총 문답·1989 서한", f"⑧ 적당한 가격: 이익수익률 {ey:.1f}% vs 10년 국채 약 {bond:.1f}%", ramp(ey, bond, bond * 2),
                   "📖 국채보다 나아야 → ⚖️ 국채 이하 0점 · 국채의 2배↑ 만점", orig=False))
    elif per is not None:
        b.append(C("주총 문답·1989 서한", "⑧ 가격: 적자 — 버핏은 사지 않음", 0.0))
    else:
        b.append(C("주총 문답·1989 서한", "⑧ 가격: PER 없음", None))
    # ⑨ 가격 결정력 — 불황에도 이익률이 지켜지나 (2010 FCIC 인터뷰: '사업 평가에서 가장 중요한 건 가격 결정력')
    om = [v for _, v in yr_vals(by, "opm", 10)] or last(F["opm"], 10)
    if fin:
        b.append(C("2010 FCIC 인터뷰", "⑨ 가격 결정력: 금융업 — 제외", None, na=True))
    elif len(om) >= 4 and sum(om) > 0:
        avg = sum(om) / len(om)
        r = min(om) / avg
        b.append(C("2010 FCIC 인터뷰", f"⑨ 가격 결정력: 가장 나쁜 해 영업이익률 {min(om):.1f}% ÷ 평균 {avg:.1f}% = {r:.2f}", ramp(r, 0.25, 0.75),
                   "⚖️ 나쁜 해에도 평균의 75%↑ 만점 · 25%↓ 0점", orig=False))
    else:
        b.append(C("2010 FCIC 인터뷰", "⑨ 가격 결정력: 이익률 4년치 미만", None))
    todo = ["사업을 이해하는가 — 10년 뒤 모습을 그릴 수 있는가 (1977 서한 ①, '능력의 범위' 1996 서한)",
            "장기 전망이 좋은가 — 가격을 올려도 고객이 떠나지 않는 해자 (1977 ② · 2007 서한 '해자')",
            "경영진이 정직하고 유능한가 (1977 ③) · 남는 돈을 주주에게 이롭게 쓰는가 (자본 배분, 1984·1987 서한)",
            "10년 동안 시장이 문을 닫아도 들고 있을 수 있는가 (1996 서한)"]
    return b, todo


# ════════════════════════════════════════════════════════════════
FISHER_GATE = 0.05     # 매출 연평균 성장 5%(명목 경제성장 수준) 미만이면 피셔가 말하는 '성장 기업'이 아님 → 피셔 점수 최대 40%


def fisher(F):
    """피셔는 '평균보다 훨씬 빨리 크는 회사'만 본다 — 2026-11 기준선 강화(이전 버전이 너무 후했음)
       · 성장·이익률 만점선을 올림 (매출·이익 15%↑, 이익률 20%↑)  · 매출 성장 5% 미만이면 피셔 점수 상한 40%"""
    f, by, fin = [], F["by"], F["fin_co"]
    CS, CI = "『위대한 기업에 투자하라』", "『보수적인 투자자는 마음이 편하다』"
    rv = [v for _, v in yr_vals(by, "rev", 10)] or last(F["rev"], 10)
    sg = cagr(rv[0], rv[-1], len(rv) - 1) if len(rv) >= 3 else None
    f.append(C(CS + " ①", f"① 매출 성장: 연평균 {sg * 100:+.1f}% ({len(rv) - 1}년)", ramp(sg, 0.05, 0.15),
               "📖 '수년간 평균보다 상당히 높은 매출 성장' → ⚖️ 15%↑ 만점(명목 경제성장의 3배) · 5%↓ 0점", orig=False)
             if sg is not None else C(CS + " ①", "① 매출 성장: 3년치 미만", None))
    ov = [v for _, v in yr_vals(by, "op", 10)] or last(F["op"], 10)
    og = cagr(ov[0], ov[-1], len(ov) - 1) if len(ov) >= 3 else None
    if len(ov) >= 3:
        f.append(C(CS + " ①⑤", f"② 이익 성장: 영업이익 {f1(ov[0], 0)} → {f1(ov[-1], 0)}" + (f" (연 {og * 100:+.1f}%)" if og is not None else " (적자 구간 포함)"),
                   0.0 if og is None else ramp(og, 0.05, 0.15), "⚖️ 매출만큼(15%↑) 이익도 커야 · 5%↓ 0점", orig=False))
    else:
        f.append(C(CS + " ①⑤", "② 이익 성장: 3년치 미만", None))
    om = [v for _, v in yr_vals(by, "opm", 10)] or last(F["opm"], 10)
    if fin:
        f += [C(CS + " ⑤", "③ 이익률: 금융업 — 제외", None, na=True), C(CS + " ⑥", "④ 이익률 개선: 금융업 — 제외", None, na=True),
              C(CI + " 1차원", "⑤ 저원가: 금융업 — 제외", None, na=True)]
    elif om:
        oa = sum(om) / len(om)
        f.append(C(CS + " ⑤ · " + CI + " 3차원", f"③ 업계 최고 수준 이익률: 영업이익률 평균 {oa:.1f}% ({len(om)}년)", ramp(oa, 8, 20),
                   "⚖️ '업계 최고 수준' → 20%↑ 만점 · 8%(국내 상장사 평균 수준)↓ 0점", orig=False))
        if len(om) >= 4:
            prev, rec = sum(om[:-3]) / len(om[:-3]), sum(om[-3:]) / 3
            f.append(C(CS + " ⑥", f"④ 이익률 개선: 최근 3년 {rec:.1f}% vs 이전 {prev:.1f}%", ramp(rec - prev, -2, 1),
                       "⚖️ 이전보다 1%p↑ 높아져야 만점 · 2%p↓ 떨어지면 0점", orig=False))
            r = min(om) / oa if oa > 0 else 0
            f.append(C(CI + " 1차원", f"⑤ 저원가 생산자: 가장 나쁜 해 이익률 {min(om):.1f}% (평균의 {r * 100:.0f}%)", ramp(r, 0.3, 0.75),
                       "⚖️ 불황에도 이익률이 평균의 75%↑ 만점 · 30%↓ 0점", orig=False))
        else:
            f += [C(CS + " ⑥", "④ 이익률 개선: 4년치 미만", None), C(CI + " 1차원", "⑤ 저원가: 4년치 미만", None)]
    else:
        f += [C(CS + " ⑤", "③ 이익률: 데이터 없음", None), C(CS + " ⑥", "④ 이익률 개선: 데이터 없음", None), C(CI + " 1차원", "⑤ 저원가: 데이터 없음", None)]
    sh = [v for _, v in yr_vals(by, "shares", 6) if v]
    if len(sh) >= 3:
        dil = sh[-1] / sh[0] - 1
        f.append(C(CS + " ⑬", f"⑥ 희석 없음: 주식 수 {dil * 100:+.1f}% ({len(sh)}년)", ramp(dil, 0.10, 0.02), "⚖️ 2%↓ 만점 · 10%↑ 0점", orig=False))
    else:
        f.append(C(CS + " ⑬", "⑥ 희석: 주식 수 데이터 없음", None))
    dr = [v for _, v in yr_vals(by, "dr", 6)]
    fcs = last(F["fcf"], 5)
    if fin:
        f.append(C(CI + " 1차원(재무 능력)", "⑦ 내부 자금 성장: 금융업 — 제외", None, na=True))
    elif len(dr) >= 3 and fcs:
        ch = dr[-1] - dr[0]
        s = ramp(ch, 30, 0)
        if sum(fcs) < 0:
            s = min(s, 0.3)
        f.append(C(CI + " 1차원(재무 능력)", f"⑦ 스스로 번 돈으로 성장: 부채비율 {dr[0]:.0f}% → {dr[-1]:.0f}% · {len(fcs)}년 FCF 합 {'+' if sum(fcs) >= 0 else '−'}",
                   s, "⚖️ 부채비율이 안 늘면 만점 · 30%p↑ 늘면 0점 (FCF 합이 마이너스면 최대 30%)", orig=False))
    else:
        f.append(C(CI + " 1차원(재무 능력)", "⑦ 내부 자금 성장: 데이터 없음", None))
    rel = F["per_rel"]
    f.append(C(CI + " 4차원(가격)", f"⑧ 가격 위험: 현재 PER이 자기 과거 중간값의 {rel * 100:.0f}%", ramp(rel, 1.5, 1.0),
               "📖 품질은 높은데 시장이 덜 알아줄 때가 가장 안전 → ⚖️ 과거 중간값 이하 만점 · 1.5배↑ 0점", orig=False)
             if rel is not None else C(CI + " 4차원(가격)", "⑧ 가격 위험: 과거 PER 데이터 없음", None))
    ee, eps = F["eps_est"], F["eps"]
    if ee and eps and eps[-1] and eps[-1] > 0:
        up = ee[0] / eps[-1] - 1
        f.append(C(CS + " ①", f"⑨ 앞으로의 성장: 증권사 추정 다음 해 EPS {up * 100:+.0f}%", ramp(up, 0.05, 0.15), "⚖️ +15%↑ 만점 · 5%↓ 0점", orig=False))
    else:
        f.append(C(CS + " ①", "⑨ 앞으로의 성장: EPS 추정치 없음", None))
    # 피셔 거름망 — 성장 기업이 아니면 상한(점수 계산은 heroes.score 에서 cap 으로)
    cap = None
    if sg is not None and sg < FISHER_GATE:
        cap = 0.4
        f.append(C(CS, f"🚧 피셔 거름망: 매출 성장 연 {sg * 100:+.1f}% < 5% → '성장 기업'이 아니라 피셔 점수 최대 40%", None, bonus=True))
    todo = ["CS ② 지금 제품이 다 팔린 뒤에도 매출을 키울 신제품·연구개발이 있는가", "CS ③ 연구개발이 매출로 이어지는가 · ④ 영업 조직이 강한가",
            "CS ⑦⑧ 노사 관계·임원 관계가 좋은가 · ⑨ 경영진 층이 두터운가", "CS ⑩ 원가와 회계를 꼼꼼히 관리하는가 · ⑪ 경쟁사보다 뛰어난 점이 분명한가",
            "CS ⑫ 단기 이익보다 장기를 보는가 · ⑭ 나쁜 소식도 솔직히 말하는가 · ⑮ 경영진이 정직한가 ('사실 수집'으로 주변 취재)",
            "CI 2차원 '사람': 창업가 정신과 내부 승진 문화가 있는가"]
    return f, todo, cap


# ════════════════════════════════════════════════════════════════
def munger(F):
    """찰리 멍거 — 『가난한 찰리의 연감』(1994 USC '세속적 지혜' 강연 · 1995 '인간 오판의 심리학') · 웨스코/데일리저널 주총
       '장기 수익률은 결국 그 사업의 자본수익률에 수렴한다' → 오래 높은 ROE를 빚·희석·회계 장난 없이 내는 훌륭한 기업을 공정한 가격에.
       '뒤집어라, 항상 뒤집어라' → 망하는 길(레버리지·현금 없는 이익·희석)을 먼저 지운다"""
    m, by, fin = [], F["by"], F["fin_co"]
    USC, PSY, PCA, DJ = "1994 USC 강연", "1995 '오판의 심리학'", "『가난한 찰리의 연감』", "웨스코·데일리저널 주총"
    rr = [v for _, v in yr_vals(by, "roe", 10)] or last(F["roe"], 10)
    avg = sum(rr) / len(rr) if rr else None
    if rr:
        m.append(C(USC, f"① 장기 자본수익률: {len(rr)}년 ROE 평균 {avg:.1f}%", ramp(avg, 6, 18),
                   "📖 '40년간 6% 버는 사업이면 6%, 18% 버는 사업이면 비싸게 사도 큰 결과' → 18%↑ 만점 · 6%↓ 0점"))
        if len(rr) >= 3:
            hi = sum(1 for v in rr if v >= 15)
            m.append(C(PCA, f"② 해자가 오래가나: {len(rr)}년 중 ROE 15%↑인 해 {hi}번", hi / len(rr),
                       "⚖️ 해마다 15%↑면 만점 — 한두 해 반짝이 아니라 경쟁을 버티는 해자", orig=False))
        else:
            m.append(C(PCA, "② 해자 지속: ROE 3년치 미만", None))
    else:
        m += [C(USC, "① 장기 자본수익률: 데이터 없음", None), C(PCA, "② 해자 지속: 데이터 없음", None)]
    # ③ 복리 기계 — 번 돈을 높은 수익률로 다시 굴려 장부가치가 크는가
    eqs = [v for _, v in yr_vals(by, "eqo", 10)] or [v for _, v in yr_vals(by, "eq", 10)]
    g = cagr(eqs[0], eqs[-1], len(eqs) - 1) if len(eqs) >= 4 else None
    m.append(C(DJ, f"③ 복리 재투자: 자본(장부가치) 연평균 {g * 100:+.1f}% ({len(eqs) - 1}년)", ramp(g, 0.04, 0.12),
               "⚖️ 남긴 이익을 다시 굴려 장부가치가 연 12%↑ 크면 만점 · 4%↓ 0점", orig=False)
             if g is not None else C(DJ, "③ 복리 재투자: 자본 4년치 미만", None))
    # ④ 뒤집어 보기 — 이익이 현금으로 들어오는가
    oc, nq = last(F["ocf"], 5), last(F["ni"], 5)
    if fin:
        m.append(C(PSY, "④ 이익의 질: 금융업 — 영업현금흐름 비교가 맞지 않아 제외", None, na=True))
    elif len(oc) >= 3 and len(nq) >= len(oc) and sum(nq[-len(oc):]) > 0:
        q = sum(oc) / sum(nq[-len(oc):])
        m.append(C(PSY, f"④ 뒤집어 보기 — 이익이 현금으로 들어오나: {len(oc)}년 영업현금흐름 ÷ 순이익 = {q * 100:.0f}%", ramp(q, 0.7, 1.1),
                   "📖 'EBITDA는 헛소리 이익' · 회계 장난 경계 → ⚖️ 110%↑ 만점 · 70%↓ 0점", orig=False))
    else:
        m.append(C(PSY, "④ 이익의 질: 데이터 없음", None))
    # ⑤ 레버리지 — '똑똑한 사람이 망하는 세 가지: 술·여자·레버리지'
    nc, opl = lastv(F["netcash"]), lastv(F["op"])
    if fin:
        m.append(C(PCA, "⑤ 레버리지: 금융업 — 제외", None, na=True))
    elif nc is not None and opl:
        lev = (-nc / opl) if nc < 0 and opl > 0 else (0 if nc >= 0 else 99)
        m.append(C(PCA, "⑤ 레버리지 없이: " + ("순현금" if nc >= 0 else f"순차입 = 영업이익의 {lev:.1f}배"), ramp(lev, 3, 0),
                   "📖 '똑똑한 사람이 망하는 세 가지 — 술·여자·레버리지' → ⚖️ 순현금 만점 · 영업이익 3배↑ 0점", orig=False))
    elif F["dr"]:
        m.append(C(PCA, f"⑤ 레버리지: 부채비율 {F['dr'][-1]:.0f}%", ramp(F["dr"][-1], 150, 50), "⚖️ 50%↓ 만점 · 150%↑ 0점", orig=False))
    else:
        m.append(C(PCA, "⑤ 레버리지: 데이터 없음", None))
    # ⑥ 주주 몫을 나누지 않는가 (스톡옵션·증자 비판)
    sh = [v for _, v in yr_vals(by, "shares", 6) if v]
    if len(sh) >= 3:
        dil = sh[-1] / sh[0] - 1
        m.append(C(DJ, f"⑥ 주주 몫 희석 없음: 주식 수 {dil * 100:+.1f}% ({len(sh)}년)", ramp(dil, 0.05, 0.0),
                   "⚖️ 주식 수가 안 늘면 만점 · 5%↑ 늘면 0점 (스톡옵션·유상증자로 주주 몫을 나누는 회사 경계)", orig=False))
    else:
        m.append(C(DJ, "⑥ 희석: 주식 수 데이터 없음", None))
    # ⑦ 훌륭한 기업을 공정한 가격에 — ROE가 높을수록 더 비싼 PER 허용
    per = F["per"]
    if per and per > 0:
        q_ = min(max((avg if avg is not None else 6) - 6, 0), 12) / 12
        full = 15 + 10 * q_
        m.append(C("1989 버크셔 서한(멍거의 영향)", f"⑦ 공정한 가격: PER {per:.1f}배 (ROE 반영 허용선 {full:.0f}배)", ramp(per, full * 1.6, full),
                   "📖 '적당한 기업을 싸게보다 훌륭한 기업을 공정한 가격에' → ⚖️ ROE 18%면 25배↓ 만점(40배↑ 0점), ROE 6%면 15배↓(24배↑ 0점)", orig=False))
    else:
        m.append(C("1989 버크셔 서한(멍거의 영향)", "⑦ 가격: 적자이거나 PER 없음", 0.0 if per is not None else None))
    todo = ["능력의 범위 안인가 — 모르면 '너무 어려움' 바구니에 넣고 넘긴다 (USC 1994)",
            "인센티브를 보라 — 경영진 보상이 주주 이익과 같은 방향인가 ('인센티브의 힘을 과소평가하지 마라', 1995)",
            "오판 체크리스트 — 확증 편향·사회적 증거(남들이 사서)·손실 회피로 사려는 건 아닌가 (1995 '오판의 심리학')",
            "경영진이 정직하고 합리적인가 — 믿을 수 있는 사람과만 (데일리저널 주총)",
            "확신이 큰 소수 종목에 집중하고, 사고 나면 오래 앉아 기다릴 수 있는가 ('엉덩이 투자', 웨스코 주총)"]
    return m, todo


# ════════════════════════════════════════════════════════════════
def klarman(F):
    """세스 클라만 — 『안전마진』(1991) · 바우포스트 연례 서한 · 인터뷰
       가치를 여러 방법(자산·수익·현금흐름)으로 보수적으로 매기고, 그보다 크게 쌀 때만 산다. 먼저 잃지 않는 것(하방)부터 본다"""
    k, by, fin = [], F["by"], F["fin_co"]
    MS, BP = "『안전마진』", "바우포스트 서한"
    mc = F["mcap_eok"]
    eqv = lastv(F["eqo"]) or lastv(F["eq"])
    n5 = last(F["nio"], 5) or last(F["ni"], 5)
    f5 = last(F["fcf"], 5)
    vals = {}
    if eqv and eqv > 0:
        vals["자산"] = eqv
    if len(n5) >= 3:
        vals["수익"] = max(0.0, sum(n5) / len(n5) * 10)
    if len(f5) >= 3 and not fin:
        vals["현금흐름"] = max(0.0, sum(f5) / len(f5) * 10)
    if mc and len(vals) >= 2:
        iv = stx.median(list(vals.values()))
        mg = 1 - mc / iv if iv > 0 else -1.0
        det = " · ".join(f"{a} {v:,.0f}억" for a, v in vals.items())
        k.append(C(MS + " 8장", f"① 보수적 가치 대비 안전마진: 가치 중간값 {iv:,.0f}억({det}) vs 시총 {mc:,.0f}억 → 할인 {mg * 100:+.0f}%",
                   ramp(mg, 0, 0.33),
                   "📖 '가치는 하나의 숫자가 아니라 범위, 여러 방법으로 보수적으로' → ⚖️ 자산(자본)·수익(5년 평균 순이익×10)·현금흐름(5년 평균 FCF×10) 중간값보다 33%↑ 싸면 만점 · 할인 없으면 0점",
                   orig=False))
    else:
        k.append(C(MS + " 8장", "① 안전마진: 가치 계산에 필요한 데이터 부족", None))
    # ② 정상화 FCF 수익률 — 한 해가 아니라 5년 평균 현금으로
    if fin:
        k.append(C(MS + " 8장", "② FCF 수익률: 금융업 — 제외", None, na=True))
    elif len(f5) >= 3 and mc:
        fy = sum(f5) / len(f5) / mc * 100
        k.append(C(MS + " 8장", f"② 5년 평균 FCF 수익률 {fy:.1f}%", ramp(fy, 3, 10),
                   "📖 '사업 가치의 핵심은 미래 현금흐름의 현재가치' → ⚖️ 10%↑ 만점 · 3%↓ 0점 (성장을 가정하지 않고도 싼가)", orig=False))
    else:
        k.append(C(MS + " 8장", "② FCF 수익률: 데이터 없음", None))
    # ③ 하방 — 자산이 받쳐 주는가
    pbr = F["pbr"]
    k.append(C(MS + " 6장", f"③ 하방 받침: PBR {pbr:.2f}배", ramp(pbr, 1.5, 0.7),
               "📖 '얼마나 벌까보다 얼마나 잃을 수 있나를 먼저' → ⚖️ PBR 0.7↓ 만점 · 1.5↑ 0점", orig=False)
             if pbr else C(MS + " 6장", "③ 하방 받침: PBR 없음", None))
    # ④ 재무 생존력 — 레버리지는 안전마진을 갉아먹는다
    if fin:
        k.append(C(MS, "④ 재무 생존력: 금융업 — 제외", None, na=True))
    else:
        dr, cr = lastv(F["dr"]), lastv(F["cr"])
        parts = [x for x in (ramp(dr, 150, 50), ramp(cr, 100, 150)) if x is not None]
        k.append(C(MS, f"④ 재무 생존력: 부채비율 {f1(dr, 0)}% · 유동비율 {f1(cr, 0)}%", sum(parts) / len(parts),
                   "⚖️ 부채비율 50%↓·유동비율 150%↑ 만점 (불황에도 버텨야 싸게 산 게 의미가 있다)", orig=False)
                 if parts else C(MS, "④ 재무 생존력: 데이터 없음", None))
    # ⑤ 소외·역발상 — 남들이 팔 때
    r1 = F["ret1y"]
    k.append(C(MS + " 9장", f"⑤ 소외된 종목: 1년 주가 {r1 * 100:+.0f}%", ramp(r1, 0.4, -0.1),
               "📖 '기회는 인기 없고 남들이 억지로 팔 때' → ⚖️ 1년 −10%↓ 만점 · +40%↑ 0점", orig=False)
             if r1 is not None else C(MS + " 9장", "⑤ 소외 여부: 1년 주가 데이터 없음", None))
    # ⑥ 가치 함정 피하기 — 싸도 가치가 녹아내리면 안 된다
    rv = [v for _, v in yr_vals(by, "rev", 6)] or last(F["rev"], 6)
    sg = cagr(rv[0], rv[-1], len(rv) - 1) if len(rv) >= 3 else None
    k.append(C(BP, f"⑥ 가치 함정 아님: 매출 연평균 {sg * 100:+.1f}% ({len(rv) - 1}년)", ramp(sg, -0.05, 0.0),
               "⚖️ 매출이 줄지 않으면 만점 · 연 −5%↓ 0점 (싸 보여도 사업 가치가 녹는 종목 경계)", orig=False)
             if sg is not None else C(BP, "⑥ 가치 함정: 매출 3년치 미만", None))
    todo = ["절대 수익 — 시장보다 덜 빠지는 게 아니라 '돈을 잃지 않는 것'이 목표인가 (『안전마진』 1장)",
            "살 게 없으면 현금으로 기다릴 수 있는가 — 바우포스트는 현금 비중 30~50%도 감수",
            "강제 매도·구조조정·분할·지수 편출처럼 '가격이 가치와 상관없이 눌린' 사정이 있는가 (『안전마진』 9~10장)",
            "가치를 숫자 하나가 아니라 범위로 봤는가 — 가장 나쁜 시나리오에서도 버틸 가격인가",
            "가치가 드러날 계기(자산 매각·자사주·분할)가 있는가 (『안전마진』 10장 촉매)"]
    return k, todo


# ════════════════════════════════════════════════════════════════
def price(F):
    """T. 로 프라이스 2세 — '성장주 투자의 아버지' (1939 배런스 기고 'Picking Growth Stocks', 1973 'The New Era for Investors')
       성장주 = 이익이 경기 순환마다 새 고점을 찍고 경제보다 빨리 크는 회사, 자본이익률이 높고, 너무 비싸게는 사지 않는다"""
    p, by = [], F["by"]
    TP = "로 프라이스 1939 '성장주 고르기'"
    e = [v for _, v in yr_vals(by, "eps", 10)] or last(F["eps"], 10)
    eg = cagr(e[0], e[-1], len(e) - 1) if len(e) >= 4 else None
    p.append(C(TP, f"① 장기 이익 성장: EPS 연평균 {eg * 100:+.1f}% ({len(e) - 1}년)", ramp(eg, 0.03, 0.12),
               "📖 '이익이 경제·물가보다 빨리 크는 회사' → ⚖️ 12%↑ 만점 · 3%(물가)↓ 0점", orig=False)
             if eg is not None else C(TP, "① 장기 이익 성장: 4년치 미만이거나 적자 구간", 0.0 if len(e) >= 4 else None))
    if len(e) >= 6:
        rec, old = max(e[-3:]), max(e[:-3])
        r = rec / old if old > 0 else (1.0 if rec > 0 else 0.0)
        p.append(C(TP, f"② 사이클마다 새 고점: 최근 3년 최고 EPS가 그 이전 최고의 {r * 100:.0f}%", ramp(r, 0.7, 1.0),
                   "📖 '경기 순환의 고점마다 이익이 전 고점을 넘는다' (성장주의 정의) → 넘으면 만점 · 70%↓ 0점"))
    else:
        p.append(C(TP, "② 사이클마다 새 고점: EPS 6년치 미만", None))
    rr = ([v for _, v in yr_vals(by, "roe", 3)] or last(F["roe"], 3))
    if rr:
        ra = sum(rr) / len(rr)
        p.append(C(TP, f"③ 높은 자본이익률: 최근 {len(rr)}년 ROE 평균 {ra:.1f}%", ramp(ra, 8, 18),
                   "📖 '높은 투하자본 수익률' → ⚖️ 18%↑ 만점 · 8%↓ 0점", orig=False))
    else:
        p.append(C(TP, "③ 자본이익률: 데이터 없음", None))
    rv = [v for _, v in yr_vals(by, "rev", 6)] or last(F["rev"], 6)
    ov = [v for _, v in yr_vals(by, "op", 6)] or last(F["op"], 6)
    sg = cagr(rv[0], rv[-1], len(rv) - 1) if len(rv) >= 3 else None
    og = cagr(ov[0], ov[-1], len(ov) - 1) if len(ov) >= 3 else None
    if sg is not None and len(ov) >= 3:
        d = (og - sg) if og is not None else -0.1
        p.append(C(TP, f"④ 이익률을 지키며 성장: 영업이익 성장 − 매출 성장 = {d * 100:+.1f}%p", ramp(d, -0.05, 0),
                   "📖 '경쟁이 치열해져 이익률이 깎이는 산업은 피한다' → ⚖️ 이익이 매출만큼 크면 만점 · 5%p↓ 뒤처지면 0점", orig=False))
    else:
        p.append(C(TP, "④ 이익률 유지: 데이터 없음", None))
    per = F["per"]
    if per and per > 0:
        p.append(C("로 프라이스 1973 'New Era'", f"⑤ 성장주라도 과한 값은 안 냄: PER {per:.1f}배", ramp(per, 40, 25),
                   "📖 1973년 '인기 성장주가 너무 비싸졌다'며 매도 → ⚖️ 25배↓ 만점 · 40배↑ 0점", orig=False))
    else:
        p.append(C("로 프라이스 1973 'New Era'", "⑤ 가격: 적자이거나 PER 없음", 0.0 if per is not None else None))
    # ⑥ 성장의 계절 — 성장 속도가 꺾이면 '가을' (1939 기고의 기업 생애주기: 성장기 → 성숙기 → 쇠퇴기)
    if len(e) >= 7 and all(v > 0 for v in e[-7:]):
        rn, ro = cagr(e[-4], e[-1], 3), cagr(e[-7], e[-4], 3)
        p.append(C(TP, f"⑥ 성장의 계절: 최근 3년 EPS 연 {rn * 100:+.0f}% vs 그 전 3년 연 {ro * 100:+.0f}%", ramp(rn - ro, -0.10, 0),
                   "📖 '성장이 느려지기 시작하면 성장주의 가을 — 성숙기 회사는 판다' → ⚖️ 속도 유지 만점 · 10%p↓ 둔화 0점", orig=False))
    else:
        p.append(C(TP, "⑥ 성장의 계절: 흑자 EPS 7년치 미만", None))
    todo = ["산업 자체가 커지는가 — 성숙·쇠퇴 산업의 1등보다 성장 산업의 좋은 회사 (1939 기고)",
            "정부 규제·원자재 가격에 이익이 휘둘리지 않는가", "성장이 끝나 가는 신호(이익률 하락·신제품 부재)가 보이면 판다 — '성장주의 가을'"]
    return p, todo


# ════════════════════════════════════════════════════════════════
def druckenmiller(F):
    """스탠리 드러켄밀러 — 『새로운 시장의 마법사들』(1992) 인터뷰 · 2015 로스트트리 강연 · Sohn 컨퍼런스 · 2023 노르웨이 국부펀드 인터뷰
       책은 안 썼지만 원칙은 일관됨: 지금이 아니라 18개월 뒤 이익을 보고, 가격 흐름(시장이 먼저 안다)을 존중하며,
       먼저 자본을 지키고 확신이 서면 크게. 밸류에이션으로 타이밍을 잡지 않는다"""
    d = []
    MW, LT, NB = "『새로운 시장의 마법사들』", "2015 로스트트리 강연", "2023 노르웨이 국부펀드 인터뷰"
    # ① 18개월 뒤 이익
    ee, eps = F["eps_est"], F["eps"]
    fg, txt = None, ""
    if ee and eps and eps[-1] and eps[-1] > 0:
        n = min(2, len(ee))
        fg = (ee[n - 1] / eps[-1]) ** (1 / n) - 1 if ee[n - 1] > 0 else -1.0
        txt = f"① 18개월 뒤 이익: 증권사 추정 EPS 연 {fg * 100:+.0f}% ({n}년 앞까지)"
    elif F["per"] and F.get("fper") and F["per"] > 0 and F["fper"] > 0:
        fg = F["per"] / F["fper"] - 1
        txt = f"① 18개월 뒤 이익: PER {F['per']:.1f} → 추정 PER {F['fper']:.1f} (이익 {fg * 100:+.0f}%)"
    d.append(C(LT, txt, ramp(fg, 0, 0.25), "📖 '현재가 아니라 18개월 뒤 모습을 그려라' → ⚖️ 연 25%↑ 만점 · 0%↓ 0점", orig=False)
             if fg is not None else C(LT, "① 18개월 뒤 이익: 증권사 추정치 없음", None))
    # ② 이익 변곡 — 분기 이익이 돌아서거나 빨라지는가
    q = F.get("q_eps") or []
    if len(q) >= 5 and q[-5] > 0 and q[-1] > 0:
        yoy = q[-1] / q[-5] - 1
        acc = (yoy - (q[-2] / q[-6] - 1)) if len(q) >= 6 and q[-6] > 0 and q[-2] > 0 else None
        s = ramp(yoy, 0, 0.25) if acc is None else (ramp(yoy, 0, 0.25) + ramp(acc, -0.15, 0.05)) / 2
        d.append(C(MW, f"② 이익 변곡: 최근 분기 EPS 전년 대비 {yoy * 100:+.0f}%" + (f" · 직전 분기보다 {acc * 100:+.0f}%p" if acc is not None else ""), s,
                   "📖 '이익이 바뀌는 변곡점을 남보다 먼저' → ⚖️ +25%↑이면서 빨라지면 만점", orig=False))
    elif len(q) >= 5 and q[-5] <= 0 < q[-1]:
        d.append(C(MW, f"② 이익 변곡: 분기 적자 → 흑자 전환 ({f1(q[-5], 0)} → {f1(q[-1], 0)})", 0.7, "⚖️ 흑자 전환 = 변곡 (70%)", orig=False))
    elif len(q) >= 5:
        d.append(C(MW, "② 이익 변곡: 최근 분기 적자", 0.0, "⚖️ 이익이 꺾이는 중"))
    elif F.get("q_yoy") is not None:
        d.append(C(MW, f"② 이익 변곡: 최근 분기 이익 전년 대비 {F['q_yoy'] * 100:+.0f}%", ramp(F["q_yoy"], 0, 0.25), "⚖️ +25%↑ 만점 · 0%↓ 0점", orig=False))
    else:
        d.append(C(MW, "② 이익 변곡: 분기 데이터 없음", None))
    # ③ 가격이 먼저 말해 준다 — 추세
    gap, hi, cl = F.get("ma200_gap"), F.get("hi52"), F["close"]
    if gap is not None:
        d.append(C(MW, f"③ 가격 흐름: 주가가 200일 평균보다 {gap * 100:+.0f}%", ramp(gap, -0.05, 0.10),
                   "📖 '시장이 먼저 안다 — 가격이 이야기와 다르면 가격을 믿어라' → ⚖️ 200일선 위 10%↑ 만점 · 5%↓ 아래 0점", orig=False))
    elif hi and cl:
        d.append(C(MW, f"③ 가격 흐름: 52주 최고가의 {cl / hi * 100:.0f}%", ramp(cl / hi, 0.70, 0.95), "⚖️ 95%↑ 만점 · 70%↓ 0점", orig=False))
    else:
        d.append(C(MW, "③ 가격 흐름: 주가 데이터 없음", None))
    # ④ 상대 강도 — 주도하는 종목인가
    r1 = F["ret1y"]
    d.append(C(NB, f"④ 주도주인가: 1년 주가 {r1 * 100:+.0f}%", ramp(r1, 0, 0.30),
               "📖 '밸류에이션으로 타이밍을 잡지 마라, 이기는 쪽에 서라' → ⚖️ 1년 +30%↑ 만점 · 0%↓ 0점", orig=False)
             if r1 is not None else C(NB, "④ 주도주: 1년 주가 데이터 없음", None))
    # ⑤ 자본 보존 — 먼저 살아남는다
    mdd = F.get("mdd1y")
    d.append(C(MW, f"⑤ 자본 보존: 최근 1년 최대 낙폭 −{mdd * 100:.0f}%", ramp(mdd, 0.45, 0.20),
               "📖 '장기 수익은 자본 보존과 홈런에서 나온다' → ⚖️ 낙폭 20%↓ 만점 · 45%↑ 0점", orig=False)
             if mdd is not None else C(MW, "⑤ 자본 보존: 1년 일봉 없음", None))
    todo = ["유동성 방향 — '주가를 움직이는 건 이익이 아니라 유동성(연준)'. 지금 금리·유동성이 이 종목 편인가 (『새로운 시장의 마법사들』)",
            "18개월 뒤 이 산업의 그림 — 지금 숫자가 아니라 그때 이익이 어디 있을지 두 문장으로",
            "확신이 크면 크게, 아니면 작게 — '맞았을 때 얼마 버나·틀렸을 때 얼마 잃나'가 중요 (소로스에게 배운 것)",
            "산 이유가 틀렸으면 가격 불문 바로 정리 — 본전 생각 금지",
            "거품 끝물·과열 신호(모두가 아는 이야기)가 아닌가"]
    return d, todo


# ════════════════════════════════════════════════════════════════
def templeton(F):
    """존 템플턴 — 16계명(1993) · 『템플턴 플랜』 · 『존 템플턴의 가치투자 전략』(로렌 템플턴, 2008) · 펀드 보고서
       '가장 많이 쓴 가치 잣대는 앞으로 벌 이익 대비 가격' + '비관이 극에 달했을 때 사라' + '우량주 속에서 바겐을 찾아라'
       → 성장하는 회사가 일시적 비관으로 싸졌을 때 (사진 분류대로 성장 쪽에 둠)"""
    t, by = [], F["by"]
    TW, R16, TP = "『존 템플턴의 가치투자 전략』", "템플턴 16계명", "『템플턴 플랜』"
    per, cl = F["per"], F["close"]
    # ① 지금 PER이 자기 5년 평균보다 낮은가
    r5 = F.get("per_rel5")
    t.append(C(TW, f"① 자기 과거보다 싼가: 현재 PER = 최근 5년 평균 PER의 {r5 * 100:.0f}%", ramp(r5, 1.2, 0.7),
               "📖 'PER을 그 회사의 과거 PER과 비교' → ⚖️ 5년 평균의 70%↓ 만점 · 120%↑ 0점", orig=False)
             if r5 is not None else C(TW, "① 과거 PER 비교: 5년 PER 데이터 없음", None))
    # ② 12개월이 아니라 5년 평균 이익으로 본 PER
    e = [v for _, v in yr_vals(by, "eps", 10)] or last(F["eps"], 10)
    e5 = e[-5:]
    if cl and len(e5) >= 3 and sum(e5) > 0:
        pe5 = cl / (sum(e5) / len(e5))
        t.append(C(TP, f"② 5년 평균 이익 기준 PER {pe5:.1f}배", ramp(pe5, 20, 10),
                   "📖 '12개월 이익 대신 최근 5년 이익으로 — 경기 왜곡을 지운다' → ⚖️ 10배↓ 만점 · 20배↑ 0점", orig=False))
    else:
        t.append(C(TP, "② 5년 평균 이익 PER: 적자이거나 데이터 부족", 0.0 if len(e5) >= 3 else None))
    # ③ 앞으로 벌 이익 대비 가격 (5년 뒤 예상 EPS)
    gs = [x for x in (F["eg"], (F["eps_est"][0] / e[-1] - 1) if F["eps_est"] and e and e[-1] > 0 else None) if x is not None]
    if cl and e and e[-1] > 0 and gs:
        g = max(0.0, min(min(gs), 0.25))
        fut = e[-1] * (1 + g) ** 5
        x = cl / fut
        t.append(C(TW, f"③ 미래 이익 대비 가격: 5년 뒤 예상 EPS {fut:,.0f}(연 {g * 100:.0f}% 가정)의 {x:.1f}배", ramp(x, 15, 8),
                   "📖 '가장 많이 쓴 잣대는 앞으로 벌 이익 대비 가격' → ⚖️ 8배↓ 만점 · 15배↑ 0점 (성장률은 과거·추정 중 작은 값, 25% 상한)", orig=False))
    else:
        t.append(C(TW, "③ 미래 이익 대비 가격: 적자이거나 데이터 부족", 0.0 if e and e[-1] <= 0 else None))
    # ④ 최대 비관
    hi = F.get("hi52")
    if hi and cl:
        dd = 1 - cl / hi
        t.append(C(R16, f"④ 비관 속에서 사기: 52주 최고가 대비 −{dd * 100:.0f}%", ramp(dd, 0.05, 0.35),
                   "📖 '비관이 극에 달했을 때가 최고의 매수 시점' → ⚖️ 고점 대비 −35%↓ 만점 · −5% 이내 0점", orig=False))
    else:
        t.append(C(R16, "④ 비관 여부: 52주 최고가 데이터 없음", None))
    # ⑤ 우량주 속 바겐 — 이익이 꾸준히 크는가
    e6 = e[-6:]
    if len(e6) >= 4:
        ups = sum(1 for a, b in zip(e6, e6[1:]) if b > a)
        t.append(C(R16, f"⑤ 우량주 속 바겐: 최근 {len(e6) - 1}번 중 {ups}번 EPS 증가", ups / (len(e6) - 1),
                   "📖 '싼 주식이 아니라 우량주 속에서 바겐을' → 해마다 이익이 늘면 만점"))
    else:
        t.append(C(R16, "⑤ 이익 꾸준함: 4년치 미만", None))
    # ⑥ 이익률이 과거보다 나은가 (일시적 비관인지 구조적 쇠퇴인지)
    om = [v for _, v in yr_vals(by, "opm", 6)] or last(F["opm"], 6)
    if len(om) >= 3 and not F["fin_co"]:
        base = sum(om[:-1]) / len(om[:-1])
        t.append(C(TW, f"⑥ 일시적 비관인가: 최근 영업이익률 {om[-1]:.1f}% vs 이전 평균 {base:.1f}%", ramp(om[-1] - base, -3, 0),
                   "⚖️ 이익률이 과거 평균 이상이면 만점 · 3%p↓ 0점 (주가만 빠지고 사업은 멀쩡해야)", orig=False))
    else:
        t.append(C(TW, "⑥ 이익률 비교: 금융업이거나 3년치 미만", None, na=F["fin_co"]))
    todo = ["비관의 이유가 일시적인가 — 사업 자체가 망가진 건 아닌가 (16계명 '모두가 팔 때')",
            "나라·업종을 넘어 비교했나 — 다른 시장의 같은 업종보다도 싼가 (글로벌 바겐 헌팅)",
            "세금·물가를 뺀 '실질 총수익'으로 봐도 남는가 (16계명 1)",
            "'이번엔 다르다' — 가장 위험한 네 마디를 내가 하고 있지 않은가",
            "분산했는가 — 아무리 공부해도 틀릴 수 있다 (16계명 '분산')"]
    return t, todo


# ════════════════════════════════════════════════════════════════
def lynch_cat(F) -> str:
    """『전설로 떠나는 월가의 영웅』 7장 6분류 — 이익 성장률 기준(저성장 2~4% · 대형우량 10~12% · 고성장 20~25%)"""
    ni = [v for _, v in yr_vals(F["by"], "ni", 10)] or F["ni"]
    if len(ni) >= 3 and any(v <= 0 for v in ni[-4:-1]) and ni[-1] > 0:
        return "회생주"
    if F["pbr"] is not None and F["pbr"] < 0.6 and (F["roe_avg"] is None or F["roe_avg"] < 8):
        return "자산주"
    op = [v for _, v in yr_vals(F["by"], "op", 10)] or F["op"]
    if len(op) >= 4:                                   # 이익이 경기 따라 크게 꺾인 해가 있으면(성장 자체는 변동으로 안 봄)
        drops = sum(1 for a, b in zip(op, op[1:]) if a > 0 and b < a * 0.7)
        if min(op) <= 0 or drops >= 2:
            return "경기순환주"
    g = F["eg"]
    if g is not None and g >= 0.15:
        return "고성장주"
    if g is not None and g >= 0.06 and (F["mcap_eok"] or 0) >= 10000:
        return "대형우량주"
    if g is not None and g < 0.06 and (F["dy"] or 0) >= 2:
        return "저성장주"
    return "보통주(중간)"


def lynch(F):
    l, by, fin = [], F["by"], F["fin_co"]
    OU, BS, LE = "『전설로 떠나는 월가의 영웅』", "『이기는 투자』", "『Learn to Earn』"
    per, dy, mc, g = F["per"], F["dy"] or 0, F["mcap_eok"], F["eg"]
    cat = lynch_cat(F)
    # ① (이익성장률 + 배당수익률) ÷ PER — 13장 : 1↓ 나쁨 · 1.5 괜찮음 · 2↑ 아주 좋음
    if per and per > 0 and g is not None:
        x = (max(g, 0) * 100 + dy) / per
        l.append(C(OU + " 13장", f"① (이익성장 {g * 100:.0f}% + 배당 {dy:.1f}%) ÷ PER {per:.1f} = {x:.2f}", ramp(x, 1, 2), "📖 2↑ 아주 좋음 · 1↓ 나쁨"))
    else:
        l.append(C(OU + " 13장", "① (성장+배당)/PER: 적자·데이터 없음", 0.0 if per is not None and per <= 0 else None))
    # ② PER이 자기 역사보다 낮은가 — 15장
    rel = F["per_rel"]
    l.append(C(OU + " 15장", f"② PER이 자기 과거 중간값의 {rel * 100:.0f}% (과거 {F['per_hist_n']}년)", ramp(rel, 1.5, 1.0),
               "📖 '이 회사 역사에 비해 PER이 높은가' → ⚖️ 중간값 이하 만점 · 1.5배↑ 0점", orig=False)
             if rel is not None else C(OU + " 15장", "② 과거 PER 비교: 데이터 없음", None))
    # ③ 이익이 꾸준히 느는가 — 15장 '꾸준한가 들쭉날쭉한가' · LE '주가는 결국 이익을 따라간다'
    e = [v for _, v in yr_vals(by, "eps", 6)] or last(F["eps"], 6)
    if len(e) >= 3:
        ups = sum(1 for a, b in zip(e, e[1:]) if b > a)
        l.append(C(OU + " 15장 · " + LE, f"③ 이익의 꾸준함: 최근 {len(e) - 1}번 중 {ups}번 EPS 증가", ups / (len(e) - 1), "📖 해마다 늘수록 만점"))
    else:
        l.append(C(OU + " 15장", "③ 이익 꾸준함: 3년치 미만", None))
    # ④ 재무 — 15장 부채/자본 · 13장 '보통 회사는 자본 75 : 부채 25'
    nc, eq = lastv(F["netcash"]), lastv(F["eq"])
    if fin:
        ta = (lastv(F["eq"]) or 0) + (lastv(F["liab"]) or 0)
        ea = lastv(F["eq"]) / ta * 100 if ta and lastv(F["eq"]) else None
        l.append(C(BS + " S&L 점검표", f"④ 금융사 자본비율: 자본 ÷ 자산 = {f1(ea)}%", ramp(ea, 2.5, 5), "📖 5%↑ 튼튼 · 2.5%↓ 0점") if ea is not None
                 else C(BS + " S&L 점검표", "④ 금융사 자본비율: 데이터 없음", None))
        l.append(C(BS + " S&L 점검표", f"⑤ 금융사 PER {f1(per)}배", ramp(per, 15, 10), "📖 10배↓ 만점 · 15배↑ 0점") if per and per > 0
                 else C(BS + " S&L 점검표", "⑤ 금융사 PER: 데이터 없음", None))
    else:
        if nc is not None and eq:
            r = max(0.0, -nc) / eq
            l.append(C(OU + " 13·15장", "④ 튼튼한 재무: " + ("순현금" if nc >= 0 else f"순차입 ÷ 자본 = {r * 100:.0f}%"), ramp(r, 0.5, 1 / 3),
                       "📖 부채 25 : 자본 75(=33%)↓ 만점 · 50%↑ 0점"))
        elif F["dr"]:
            l.append(C(OU + " 13·15장", f"④ 재무: 부채비율 {F['dr'][-1]:.0f}% (순차입 데이터 없음)", ramp(F["dr"][-1], 150, 100), "⚖️ 100%↓ 만점 · 150%↑ 0점", orig=False))
        else:
            l.append(C(OU + " 13·15장", "④ 재무: 데이터 없음", None))
        if nc is not None and mc and not F["us"]:
            l.append(C(OU + " 15장", f"⑤ 순현금 = 시총의 {nc / mc * 100:.0f}% (주가의 바닥)", ramp(nc / mc, 0, 0.3), "⚖️ 30%↑ 만점 · 순현금 없으면 0점", orig=False))
        else:
            l.append(C(OU + " 15장", "⑤ 순현금 비교: 데이터 없음", None, na=F["us"]))
    # ⑥ 자사주 매입 — 15장 · BS 황금률
    sh = [v for _, v in yr_vals(by, "shares", 6) if v]
    if len(sh) >= 3:
        ch = sh[-1] / sh[0] - 1
        l.append(C(OU + " 15장 · " + BS, f"⑥ 주식 수: {ch * 100:+.1f}% ({len(sh)}년)", ramp(ch, 0.05, -0.02), "📖 회사가 자사주를 사면 좋은 신호 → ⚖️ 2%↑ 감소 만점 · 5%↑ 증가 0점", orig=False))
    else:
        l.append(C(OU + " 15장", "⑥ 자사주·주식 수: 데이터 없음", None))
    # ⑦ 과열 아님 — 8장 '가장 인기 있는 업종의 가장 인기 있는 주식은 피하라'
    r1 = F["ret1y"]
    l.append(C(OU + " 8장", f"⑦ 과열 아님: 1년 주가 {r1 * 100:+.0f}%", ramp(r1, 1.0, 0.5), "⚖️ +50%↓ 만점 · +100%↑ 0점", orig=False)
             if r1 is not None else C(OU + " 8장", "⑦ 과열 여부: 1년 주가 데이터 없음", None))
    # ⑧ ⑨ 분류별 15장 점검표
    S = OU + " 15장 · " + cat
    peg = per / (g * 100) if per and per > 0 and g and g > 0 else None
    pegc = (lambda n: C(S, f"{n} PER이 성장률 근처: PEG {peg:.2f}", ramp(peg, 2, 1), "📖 PEG 1↓ 만점 · 2↑ 0점") if peg is not None
            else C(S, f"{n} PEG: 성장 없거나 적자", 0.0 if per else None))
    if cat == "고성장주":
        s = None if g is None else 1.0 if 0.20 <= g <= 0.25 else ramp(g, 0.10, 0.20) if g < 0.20 else ramp(g, 0.50, 0.25)
        l.append(C(S, f"⑧ 성장 속도: 연 {g * 100:.0f}%", s, "📖 20~25% 만점 · 25%↑는 오래 못 감(50%↑ 0점)"))
        l.append(pegc("⑨"))
    elif cat in ("대형우량주", "보통주(중간)"):
        ni = [v for _, v in yr_vals(by, "ni", 10)]
        if len(ni) >= 4:
            w = min(b / a - 1 for a, b in zip(ni, ni[1:]) if a > 0) if any(a > 0 for a in ni[:-1]) else -1
            l.append(C(S, f"⑧ 불황 때 성적: 가장 나빴던 해 순이익 {w * 100:+.0f}%", ramp(w, -0.5, -0.1), "📖 과거 불황을 어떻게 견뎠나 → ⚖️ −10% 이내 만점 · 반토막 0점", orig=False))
        else:
            l.append(C(S, "⑧ 불황 때 성적: 4년치 미만", None))
        l.append(pegc("⑨"))
    elif cat == "저성장주":
        dp = [v for _, v in yr_vals(by, "dps", 10)]
        if len(dp) >= 3:
            up = sum(1 for a, b in zip(dp, dp[1:]) if b >= a and b > 0) / (len(dp) - 1)
            l.append(C(S, f"⑧ 배당을 꾸준히 올렸나: {len(dp) - 1}번 중 {round(up * (len(dp) - 1))}번 유지·인상", up, "📖 늘 배당하고 정기적으로 올릴 것"))
        else:
            l.append(C(S, "⑧ 배당 이력: 데이터 없음", None))
        po = lastv(F["payout"])
        l.append(C(S, f"⑨ 배당성향 {po:.0f}%", ramp(po, 90, 50), "📖 낮을수록 안전 → ⚖️ 50%↓ 만점 · 90%↑ 0점", orig=False) if po is not None
                 else C(S, "⑨ 배당성향: 데이터 없음", None))
    elif cat == "경기순환주":
        iv, sv = last(F["inv"], 2), last(F["rev"], 2)
        if len(iv) == 2 and len(sv) == 2 and iv[0] and sv[0]:
            d = (iv[1] / iv[0] - 1) - (sv[1] / sv[0] - 1)
            l.append(C(S, f"⑧ 재고: 재고 증가율 − 매출 증가율 = {d * 100:+.0f}%p", ramp(d, 0.30, 0.05), "📖 재고가 쌓이면 경고 → ⚖️ +5%p↓ 만점 · +30%p↑ 0점", orig=False))
        else:
            l.append(C(S, "⑧ 재고: 데이터 없음", None))
        e10 = [v for _, v in yr_vals(by, "eps", 10)]
        if len(e10) >= 4 and max(e10) > 0 and e10[-1] > 0:
            r = e10[-1] / max(e10)
            l.append(C(S, f"⑨ 사이클 위치: 지금 EPS가 10년 최고의 {r * 100:.0f}%", ramp(r, 1.0, 0.6), "📖 이익 정점(PER 최저)에 사면 위험 → ⚖️ 정점의 60%↓ 만점 · 정점 0점", orig=False))
        else:
            l.append(C(S, "⑨ 사이클 위치: 적자이거나 데이터 부족", None))
    elif cat == "회생주":
        cash, li = lastv(F["cash"]), lastv(F["liab"])
        l.append(C(S, f"⑧ 버틸 현금: 현금 ÷ 부채 = {cash / li * 100:.0f}%", ramp(cash / li, 0.1, 0.5), "📖 채권자가 몰려와도 버티나 → ⚖️ 50%↑ 만점 · 10%↓ 0점", orig=False)
                 if cash is not None and li else C(S, "⑧ 버틸 현금: 데이터 없음", None))
        om = [v for _, v in yr_vals(by, "opm", 4)]
        l.append(C(S, f"⑨ 회복 중: 영업이익률 {om[-2]:.1f}% → {om[-1]:.1f}%", ramp(om[-1] - om[-2], -1, 2), "📖 비용 절감·회복 → ⚖️ +2%p↑ 만점", orig=False) if len(om) >= 2
                 else C(S, "⑨ 회복: 데이터 없음", None))
    elif cat == "자산주":
        pbr = F["pbr"]
        l.append(C(S, f"⑧ 자산 가치 대비 가격: PBR {pbr:.2f}", ramp(pbr, 1.0, 0.5), "📖 숨은 자산 → ⚖️ PBR 0.5↓ 만점 · 1↑ 0점", orig=False))
        lv = [v for _, v in yr_vals(by, "liab", 3)]
        l.append(C(S, f"⑨ 새 빚: 부채 {lv[0]:,.0f} → {lv[-1]:,.0f}억", ramp(lv[-1] / lv[0] - 1, 0.3, 0), "📖 새 빚이 자산 가치를 깎음 → ⚖️ 안 늘면 만점", orig=False)
                 if len(lv) >= 2 and lv[0] else C(S, "⑨ 새 빚: 데이터 없음", None))
    todo = ["이 회사가 왜 오를지 두 문장으로 말할 수 있는가 — '2분 연설' (OU 15장 · LE)",
            "내가 일상·업무에서 직접 써 보고 아는 회사인가 (OU 1장 · BS 황금률 2)",
            "지루하거나 꺼리는 업종이라 아직 덜 알려졌는가 · 기관 보유·애널리스트 관심이 적은가 (OU 8·15장)",
            "'다각화(diworseification)'로 엉뚱한 사업을 사들이고 있지 않은가 (OU 8장)", "임원(내부자)이 자기 돈으로 사고 있는가 (OU 8·15장)"]
    return l, todo, cat


# ════════════════════════════════════════════════════════════════
def ackman(F, filings, has_f):
    a, by, fin = [], F["by"], F["fin_co"]
    PS = "퍼싱스퀘어 원칙"
    fc = last(F["fcf"], 5)
    a.append(C(PS, f"① FCF 창출: 최근 {len(fc)}년 중 {sum(1 for v in fc if v > 0)}년 플러스", sum(1 for v in fc if v > 0) / len(fc), "📖 '잉여현금흐름을 꾸준히 만드는 회사'")
             if len(fc) >= 3 else C(PS, "① FCF: 데이터 없음", None))
    rv = [v for _, v in yr_vals(by, "rev", 10)] or last(F["rev"], 10)
    if len(rv) >= 4:
        falls = sum(1 for x, y in zip(rv, rv[1:]) if x and y < x * 0.9)
        a.append(C(PS, f"② 예측 가능성: {len(rv)}년간 매출 10%↑ 감소 {falls}번", ramp(falls, 2, 0), "📖 '단순하고 예측 가능' → ⚖️ 0번 만점 · 2번↑ 0점", orig=False))
    else:
        a.append(C(PS, "② 예측 가능성: 4년치 미만", None))
    om = [v for _, v in yr_vals(by, "opm", 10)] or last(F["opm"], 10)
    if fin:
        a.append(C(PS, "③ 진입장벽: 금융업 — 제외", None, na=True))
    elif len(om) >= 3:
        oa, rg = sum(om) / len(om), max(om) - min(om)
        a.append(C(PS, f"③ 진입장벽: 영업이익률 평균 {oa:.1f}% · 변동폭 {rg:.1f}%p", (ramp(oa, 5, 15) + ramp(rg, 15, 5)) / 2,
                   "📖 '높은 진입장벽' → ⚖️ 이익률 15%↑·변동 5%p↓ 만점", orig=False))
    else:
        a.append(C(PS, "③ 진입장벽: 3년치 미만", None))
    nc, opl = lastv(F["netcash"]), lastv(F["op"])
    if fin:
        a.append(C(PS, "④ 재무: 금융업 — 제외", None, na=True))
    elif nc is not None and opl:
        lev = (-nc / opl) if nc < 0 and opl > 0 else (0 if nc >= 0 else 99)
        a.append(C(PS, "④ 튼튼한 재무: " + ("순현금" if nc >= 0 else f"순차입 = 영업이익의 {lev:.1f}배"), ramp(lev, 4, 0),
                   "📖 '보수적인 재무 구조' → ⚖️ 순현금 만점 · 영업이익 4배↑ 0점", orig=False))
    elif F["dr"]:
        a.append(C(PS, f"④ 재무: 부채비율 {F['dr'][-1]:.0f}%", ramp(F["dr"][-1], 150, 50), "⚖️ 50%↓ 만점 · 150%↑ 0점", orig=False))
    else:
        a.append(C(PS, "④ 재무: 데이터 없음", None))
    fl, mc = lastv(F["fcf"]), F["mcap_eok"]
    if fl is not None and mc and not F["us"]:
        fy = fl / mc * 100
        a.append(C(PS, f"⑤ 매력적 가격: FCF 수익률 {fy:.1f}%", ramp(fy, 2, 6), "📖 '내재가치보다 크게 싸게' → ⚖️ FCF 수익률 6%↑ 만점 · 2%↓ 0점", orig=False))
    elif F["per"] and F["per"] > 0:
        a.append(C(PS, f"⑤ 매력적 가격: PER {F['per']:.1f}배 (FCF 수익률 대신 이익수익률 {100 / F['per']:.1f}%)", ramp(100 / F["per"], 2, 6), "⚖️ 이익수익률 6%↑ 만점 · 2%↓ 0점", orig=False))
    else:
        a.append(C(PS, "⑤ 가격: 데이터 없음", None))
    if has_f:
        ret = [x for x in filings if x.get("tag") in ("자사주", "배당")]
        dil = sum(1 for x in filings if x.get("tag") == "증자·CB")
        gap = bool(F["pbr"] and F["pbr"] < 1 and (F["roe_avg"] or 0) >= 8)
        s = max(0.0, min(1.0, (0.67 if ret else 0) + (0.33 if gap else 0) - (0.67 if dil else 0)))
        a.append(C(PS, "⑥ 촉매: " + (f"주주환원 공시 {len(ret)}건" if ret else "주주환원 공시 없음") + (" · PBR<1인데 ROE 8%↑(재평가 여지)" if gap else "")
                   + (f" · 희석 공시 {dil}건" if dil else ""), s, "📖 '가치가 드러날 계기' → ⚖️ 환원 공시 2/3 + 재평가 여지 1/3 − 희석", orig=False))
    elif F["target"] and F["close"]:
        up = F["target"] / F["close"] - 1
        a.append(C(PS, f"⑥ 촉매(대신 목표가 여력): {up * 100:+.0f}% — 해외는 공시 없음", ramp(up, 0, 0.2), "⚖️ +20%↑ 만점", orig=False))
    else:
        a.append(C(PS, "⑥ 촉매: 공시·목표가 없음", None, na=F["us"]))
    todo = ["시장 1등이라 가격을 정할 수 있는가 (지배적 위치)", "금리·원자재·규제처럼 통제 못 하는 위험에 덜 노출됐는가",
            "가치가 드러날 계기(구조조정·분할·경영진 교체·자사주 소각)가 보이는가", "경영진과 지배구조가 주주 편인가"]
    return a, todo
