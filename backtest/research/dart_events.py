"""공시 유형별 이벤트 스터디: 공시일 다음 거래일 시가 매수 → h일 후 종가, 유니버스 동일비중 대비 초과수익."""
import sys, pickle, re
import numpy as np, pandas as pd
sys.path.insert(0, ".")
from engine import load, START, IS_END

piv, idx = load("/tmp/claude-0/btkr/kospi_all.csv.gz", "KPI200")
keep = [c for c in piv["Close"].columns if c.endswith("0")]
C = piv["Close"][keep]; O = piv["Open"][keep]
uni, _ = pickle.load(open("kr_pit.pkl", "rb"))
dates = C.index
D = "/tmp/claude-0/btdart/"
fil = pd.read_csv(D + "dart_filings.csv.gz", dtype={"code": str, "rcept_dt": str, "rcept_no": str})
ins = pd.read_csv(D + "dart_insider.csv.gz", dtype={"code": str, "rcept_dt": str})
dps = pd.read_csv(D + "dart_dps.csv.gz", dtype={"code": str})
print("공시", len(fil), "지분", len(ins), "배당", len(dps))

def norm(s): return re.sub(r"\s+", "", str(s))
fil["nm"] = fil["report_nm"].map(norm)
fil = fil[~fil["nm"].str.startswith("[")]          # 정정·첨부 등 제외(원공시만)
RULES = [
    ("자사주신탁", r"자기주식취득신탁계약체결결정"),
    ("자사주취득", r"^(주요사항보고서\()?자기주식취득결정"),
    ("자사주소각", r"주식소각결정"),
    ("무상증자", r"^(주요사항보고서\()?무상증자결정"),
    ("유무상증자", r"유무상증자결정"),
    ("배당결정", r"현금ㆍ현물배당결정|현금배당결정"),
    ("액면분할", r"주식분할결정"),
    ("공급계약", r"단일판매ㆍ공급계약체결"),
    ("밸류업", r"기업가치제고계획"),
    ("유상증자", r"^(주요사항보고서\()?유상증자결정"),
    ("전환사채", r"전환사채권발행결정"),
    ("BW", r"신주인수권부사채권발행결정"),
    ("교환사채", r"교환사채권발행결정"),
    ("자사주처분", r"자기주식처분결정"),
    ("감자", r"감자결정"),
    ("잠정실적", r"영업\(잠정\)실적"),
]
ev = []
for name, pat in RULES:
    m = fil[fil["nm"].str.contains(pat)]
    for d, c in zip(m["rcept_dt"], m["code"]):
        ev.append((name, c, pd.Timestamp(d)))
# 배당 증가: FY Y 결산배당 결정(다음 해 1~4월 첫 배당결정 공시) & DPS(Y) > DPS(Y-1)
def num(x):
    try: return float(str(x).replace(",", "").replace("-", "") or "nan")
    except: return np.nan
dmap = {}
for _, r in dps.iterrows():
    y = int(r.year)
    for k, v in ((y, r.dps_y), (y - 1, r.dps_y1), (y - 2, r.dps_y2)):
        if (r.code, k) not in dmap and np.isfinite(num(v)):
            dmap[(r.code, k)] = num(v)
divf = fil[fil["nm"].str.contains(r"현금ㆍ현물배당결정|현금배당결정")].copy()
divf["dt"] = pd.to_datetime(divf["rcept_dt"])
for (c, yr), g in divf[divf.dt.dt.month <= 4].groupby([divf.code, divf.dt.dt.year]):
    fy = yr - 1
    a, b = dmap.get((c, fy)), dmap.get((c, fy - 1))
    if a is None or b is None or (b > 0 and not (0.2 < a / b < 5)):   # 액면분할 등으로 비교 불가 제외
        continue
    d = g.dt.min()
    if a > b * 1.05 and b > 0: ev.append(("배당증가(5%↑)", c, d))
    if a > b * 1.2 and b > 0: ev.append(("배당증가(20%↑)", c, d))
    if a < b * 0.95: ev.append(("배당감소", c, d))
# 임원·주요주주 매수/매도 (첫 보고는 제외: 보유수량 == 증감수량)
for col in ("irds_cnt", "rate", "irds_rate"):
    ins[col] = pd.to_numeric(ins[col].astype(str).str.replace(",", ""), errors="coerce")
first_rep = ins["irds_cnt"].abs() >= 0  # placeholder
ins = ins.dropna(subset=["irds_cnt"])
buy = ins[(ins.irds_cnt > 0) & (ins.irds_rate < ins.rate - 1e-9)]
sell = ins[ins.irds_cnt < 0]
for nm, g in (("임원·대주주 매수", buy), ("임원·대주주 매도", sell)):
    for (c, d), _ in g.groupby(["code", "rcept_dt"]):
        ev.append((nm, c, pd.Timestamp(d)))
# 같은 회사 임원 매수 3건 이상(30일 내) = 집단 매수
b2 = buy.copy(); b2["dt"] = pd.to_datetime(b2["rcept_dt"])
for c, g in b2.groupby("code"):
    ds = g["dt"].sort_values().values
    for i in range(len(ds)):
        n = ((ds >= ds[i] - np.timedelta64(30, "D")) & (ds <= ds[i])).sum()
        if n >= 3:
            ev.append(("임원 집단매수(30일 3건↑)", c, pd.Timestamp(ds[i])))
E = pd.DataFrame(ev, columns=["type", "code", "date"]).drop_duplicates()
E = E[E.code.isin(C.columns) & (E.date >= START - pd.Timedelta(days=5))]
print("이벤트", len(E))

pos = {c: i for i, c in enumerate(C.columns)}
Cv, Ov = C.values, O.values
Uv = uni.reindex(dates).fillna(False).values
def fwd(t1, h):
    """t1일 시가 → t1+h-1일 종가 수익률, 유니버스 평균 대비"""
    t2 = min(t1 + h - 1, len(dates) - 1)
    r = Cv[t2] / Ov[t1] - 1
    bench = np.nanmean(np.where(Uv[t1], r, np.nan))
    return r, bench
rows = []
for typ, c, d in E.itertuples(index=False):
    t = dates.searchsorted(d, side="right")        # 공시일 다음 거래일
    if t >= len(dates) - 1: continue
    j = pos[c]
    if not np.isfinite(Ov[t, j]) or Ov[t, j] <= 0: continue
    t0 = dates.searchsorted(d, side="left")
    day0 = Cv[min(t0, len(dates)-1), j] / Cv[t0 - 1, j] - 1 if t0 > 0 and t0 < len(dates) and dates[t0] == d else np.nan
    rec = {"type": typ, "code": c, "date": d, "t": t, "in_uni": bool(Uv[t - 1, j]), "day0": day0}
    for h in (5, 20, 60):
        if t + h - 1 >= len(dates): rec[f"x{h}"] = np.nan; continue
        r, b = fwd(t, h); rec[f"x{h}"] = r[j] - b
    rows.append(rec)
R = pd.DataFrame(rows)
R.to_pickle("dart_events.pkl")
def summ(x):
    x = x.dropna()
    return f"{x.mean():+.2%} (n={len(x)}, 승률 {(x>0).mean():.0%}, t={x.mean()/x.std()*np.sqrt(len(x)) if len(x)>2 else np.nan:.1f})"
print(f"\n{'유형':22s} | {'공시일 반응':>8s} | 20일 IS | 20일 OOS | 60일 IS | 60일 OOS")
for typ, g in R.groupby("type"):
    a, b = g[g.date <= IS_END], g[g.date > IS_END]
    print(f"{typ:22s} | {g.day0.mean():+.2%} | {summ(a.x20)} | {summ(b.x20)} | {summ(a.x60)} | {summ(b.x60)}")
