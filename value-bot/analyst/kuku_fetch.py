"""kuku_fetch.py — 쿠쿠홈시스·쿠쿠홀딩스 심층 조사용 DART/네이버 자료 (GitHub Actions에서 실행)
 - list.json 전체(2018~2026) / elestock(임원·주요주주 소유보고) / majorstock(대량보유) / hyslrSttus(최대주주) 연도별 /
   alotMatter(배당) 연도별 / 일별 시세(2021) """
import io, json, os, sys, time, zipfile
import xml.etree.ElementTree as ET
import requests

DART = "https://opendart.fss.or.kr/api"
KEY = os.environ.get("DART_API_KEY") or sys.exit("DART_API_KEY 필요")
UA = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"}
OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)

z = zipfile.ZipFile(io.BytesIO(requests.get(f"{DART}/corpCode.xml", params={"crtfc_key": KEY}, timeout=60).content))
codes = {}
for el in ET.fromstring(z.read(z.namelist()[0])).iter("list"):
    sc = (el.findtext("stock_code") or "").strip()
    if sc:
        codes[sc] = el.findtext("corp_code")


def dart(path, **p):
    for _ in range(3):
        try:
            r = requests.get(f"{DART}/{path}", params={"crtfc_key": KEY, **p}, timeout=40).json()
            time.sleep(0.2)
            return r
        except Exception:
            time.sleep(2)
    return {}


def lst(cc, bgn, end):
    out, page = [], 1
    while True:
        j = dart("list.json", corp_code=cc, bgn_de=bgn, end_de=end, page_no=page, page_count=100)
        if j.get("status") != "000":
            break
        out += j["list"]
        if page >= int(j.get("total_page", 1)):
            break
        page += 1
    return out


res = {}
for t in ("284740", "192400"):
    cc = codes.get(t)
    d = {"corp_code": cc}
    d["list"] = []
    for y in range(2018, 2027):
        d["list"] += lst(cc, f"{y}0101", f"{y}1231")
    d["elestock"] = dart("elestock.json", corp_code=cc).get("list")
    d["majorstock"] = dart("majorstock.json", corp_code=cc).get("list")
    d["hyslr"] = {y: dart("hyslrSttus.json", corp_code=cc, bsns_year=str(y), reprt_code="11011").get("list") for y in range(2018, 2026)}
    d["alot"] = {y: dart("alotMatter.json", corp_code=cc, bsns_year=str(y), reprt_code="11011").get("list") for y in range(2018, 2026)}
    d["treasury"] = {y: dart("tesstkAcqsDspsSttus.json", corp_code=cc, bsns_year=str(y), reprt_code="11011").get("list") for y in range(2018, 2026)}
    d["shares"] = {y: dart("stockTotqySttus.json", corp_code=cc, bsns_year=str(y), reprt_code="11011").get("list") for y in range(2018, 2026)}
    res[t] = d
    print(t, "list", len(d["list"]), "elestock", len(d["elestock"] or []), "major", len(d["majorstock"] or []), flush=True)

# 일별 시세(2018~현재): 쿠쿠홈시스·코웨이 — 블록딜 의심일 거래량 급증 확인용
def daily(t):
    try:
        txt = requests.get("https://api.finance.naver.com/siseJson.naver", params={
            "symbol": t, "requestType": 1, "startTime": "20180101", "endTime": "20261031", "timeframe": "day"},
            headers=UA, timeout=30).text
        return json.loads(txt.replace("'", '"'))
    except Exception as e:
        return {"error": str(e)}

res["daily"] = {t: daily(t) for t in ("284740", "021240", "192400")}
json.dump(res, open(os.path.join(OUT, "kuku.json"), "w", encoding="utf-8"), ensure_ascii=False)
print("done")


# 핵심 공시 원문 일부(태그 제거) — 대주주 매각·증여·공정공시 내용 확인용
import re
DOCS = "20210622000221 20210622800063 20211104000136 20211104800078 20211122800353 20220824800277 20241227800518 20241024800499 20180514800933".split()
with open(os.path.join(OUT, "docs.txt"), "w", encoding="utf-8") as f:
    for no in DOCS:
        try:
            r = requests.get(f"{DART}/document.xml", params={"crtfc_key": KEY, "rcept_no": no}, timeout=40)
            zz = zipfile.ZipFile(io.BytesIO(r.content))
            raw = " ".join(zz.read(n).decode("utf-8", "ignore") for n in zz.namelist())
            t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw))
        except Exception as e:
            t = f"실패 {e}"
        f.write(f"\n===== {no} (길이 {len(t)}) =====\n{t[:4500]}\n")
        time.sleep(0.3)
print("docs done")


# 재무상태표·현금흐름표 전체(순현금·영업현금흐름·배당 지급액) — 쿠쿠홈시스·쿠쿠홀딩스·코웨이, 2019~2025
full = {}
for t in ("284740", "192400", "021240"):
    cc = codes.get(t)
    full[t] = {}
    for y in range(2019, 2026):
        j = dart("fnlttSinglAcntAll.json", corp_code=cc, bsns_year=str(y), reprt_code="11011", fs_div="CFS")
        full[t][y] = j.get("list") if j.get("status") == "000" else None
json.dump(full, open(os.path.join(OUT, "full.json"), "w", encoding="utf-8"), ensure_ascii=False)
print("full done")
