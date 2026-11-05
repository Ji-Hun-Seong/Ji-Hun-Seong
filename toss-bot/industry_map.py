"""한국 상장사 업종·주요제품 표 → toss-bot/data/industry_kr.csv (발굴 목록에 '무슨 회사인지' 한 줄로 보여 주는 용도)
출처: KRX KIND 상장법인목록 (회사명·종목코드·업종·주요제품). GitHub Actions 가 매주 갱신."""
import io, os, sys
import pandas as pd
import requests

URL = "https://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "industry_kr.csv")

os.makedirs(os.path.dirname(OUT), exist_ok=True)
r = requests.get(URL, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
r.raise_for_status()
df = pd.read_html(io.StringIO(r.content.decode("euc-kr", "replace")), header=0)[0]
df = df.rename(columns={"회사명": "name", "종목코드": "code", "업종": "sector", "주요제품": "product"})
df["code"] = df["code"].astype(str).str.zfill(6)
df = df[["code", "name", "sector", "product"]].fillna("")
df["product"] = df["product"].str.replace(r"\s+", " ", regex=True).str.strip()
if len(df) < 2000:
    sys.exit(f"너무 적음: {len(df)}행 — 저장 안 함")
df.sort_values("code").to_csv(OUT, index=False, encoding="utf-8")
print(len(df), "종목 저장 →", OUT)
print(df[df.code.isin(["134380", "453340", "282330", "003230", "192820", "055550"])].to_string())
