"""
빌 애크먼 매매일지(13F·인터뷰·주주서한) 기반 미국 주식 10선 → 텔레그램 "Bilackman Portfolio"
  python 13f/ackman_reco.py          # 미리보기(Actions notice)
  python 13f/ackman_reco.py --send   # 전송
환경변수: TG_TOKEN, TG_CHAT_ID
"""
import os, sys, time
import requests

MSGS = [
"""🇺🇸 <b>빌 애크먼 매매일지로 뽑은 미국 주식 10선</b>
기준일 2026-10-30 종가 · 13F 2026-06-30(8/14 제출)

<b>애크먼의 매매 습관 (13F 50개 분기, 2013~2026 분석)</b>
▪ 집중: 평균 8종목, 상위 5종목이 포트의 약 82%
▪ 보유: 평균 9분기(중앙값 6분기). 하워드휴즈 39분기, 치폴레 34분기, 레스토랑브랜즈 2014년부터 보유 중
▪ 기준: "20년 뒤에도 살아남을 사업", 단순·예측 가능, 잉여현금흐름 창출, 원자재·금리·규제에 덜 휘둘림
▪ 최근 관점(2026): AI 반도체에 쏠린 시장에서 "AI에 흔들리지 않는 우량주"를 싸게 산다. 결제·신용평가 같은 '통행료' 사업 신규 편입

<b>점수 = 확신도 35% + 밸류 35% + 질 30% − 추격 감점</b>
확신도: 13F 비중·최근 추가 여부 / 밸류: FCF수익률·선행PER·고점 대비 하락 / 질: 영업이익률·성장률·부채
6/30 이후 20% 넘게 오른 종목은 감점""",

"""📋 <b>추천 10종목 · 제안 비중</b>

<b>1. Uber (UBER) 18% — 매수</b>
13F 1위 12.7%, 2분기 +15% 추가. "이 정도 질의 사업치고 극단적으로 싸다"(8월)
$65.25 · 애크먼 공시 이후 −14% · 선행PER 14.8 · FCF수익률 5.4%
→ 애크먼이 산 가격(약 $71)보다 쌈

<b>2. Netflix (NFLX) 14% — 매수</b>
신규 4.8%. "스트리밍 전쟁은 사실상 넷플릭스가 이겼다", "고성장 유틸리티"(10/22 CNBC)
$62.08 · 공시 이후 −21% · 선행PER 16.5
→ 10종목 중 가장 많이 빠짐, 밸류 점수 1위

<b>3. Meta (META) 13% — 매수</b>
9.2%, +20% 추가. "믿기 힘들 만큼 저평가", "2027년은 놀라운 해"
$614.99 · 선행PER 17.3 · 이익률·성장 모두 최상위

<b>4. Brookfield (BN) 11% — 매수(분할)</b>
12.6%(소폭 축소). 대체자산 운용 + 보험
$39.28 · 6/30 대비 −8% · 선행PER 6.7
⚠️ 연결 부채가 커서 숫자가 복잡함

<b>5. Restaurant Brands (QSR) 10% — 매수</b>
9.6%, +14% 추가. 12년째 보유 중인 최장기 핵심
$72.41 · 선행PER 16.4 · FCF수익률 4.8% · 부채비율 높은 편""",

"""<b>6. Amazon (AMZN) 8% — 보유</b>
10.5%이지만 2분기에 −25% 줄임 → 신규라면 비중 작게
$240.35 · 선행PER 22.8

<b>7. Microsoft (MSFT) 7% — 보유, 추격 자제</b>
11.9%, +10% 추가. 그러나 6/30 이후 +40% 올라 감점
$521.91 · 선행PER 21.6 → 눌릴 때 분할

<b>8. Howard Hughes (HHH) 7% — 보유</b>
10.2%, +48% 추가. 애크먼이 '현대판 버크셔'로 키우는 지주사. 사실상 애크먼 본인에게 거는 종목
$76.23 · 부동산 개발이라 현금흐름이 들쭉날쭉

<b>9. S&P Global (SPGI) 6% — 매수(분할)</b>
신규 5.4%. 신용평가·지수 '통행료' 사업
$466.55 · 6/30 대비 +15%

<b>10. Visa (V) 6% — 보유/조정 시 매수</b>
신규 5.8%. 결제 '통행료'. 마스터카드(5.6%)와 사업이 겹쳐 하나만 선택
$413.59 · 6/30 대비 +21%

❌ <b>제외</b>
▪ Alphabet: 애크먼 전량 매도(이후 −22%)
▪ Mastercard: Visa와 중복
▪ ICE·Alcon: 6/30 이후 샀다는 보도만 있고 13F로 아직 확인 안 됨 → 11월 13F 보고 판단""",

"""⚖️ <b>현실 점검</b>
▪ 애크먼 13F 상장 11종목, 6/30 이후: <b>+7.0%</b> (S&P500 +1.4%, 나스닥100 −6.1%)
▪ 하지만 공시일(8/14)에 따라 샀다면 이 10종목 동일비중 <b>−2.7%</b> (S&P500 −2.4%)
→ 13F는 최대 45일 늦게 나와서, 그대로 따라 사면 애크먼보다 비싸게 사기 쉬움
▪ 13F 5년 수익률 약 +17%로 나스닥100보다 낮았음

📌 <b>매매 원칙 (애크먼식)</b>
① 한 번에 다 사지 말고 2~3번 나눠 사기
② 애크먼이 비중을 크게 줄이면(▼25% 이상) 같이 줄이기
③ 전량 매도 공시가 뜨면 따라 정리 검토
④ 분기마다 13F 나오면 재조정 — 다음 13F는 <b>11월 14일경</b> (이 방에 자동 알림)

※ 13F는 분기말 미국 상장주식 롱 포지션만 공개(공매도·옵션 일부·비상장 제외). 가격은 10/30 종가. 투자 자문이 아니며 최종 판단은 본인 몫.""",
]


def send(text):
    tok, chat = os.environ["TG_TOKEN"], os.environ["TG_CHAT_ID"]
    for _ in range(2):
        r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                          json={"chat_id": chat, "text": text, "parse_mode": "HTML",
                                "disable_web_page_preview": True}, timeout=30)
        j = r.json()
        new = (j.get("parameters") or {}).get("migrate_to_chat_id")
        if not r.ok and new:
            print(f"::warning::그룹이 슈퍼그룹으로 바뀜: {chat} → {new}")
            chat = str(new); continue
        if not r.ok:
            raise RuntimeError(f"텔레그램 {r.status_code}: {r.text[:200]}")
        return
    raise RuntimeError("전송 실패")


def main():
    for i, m in enumerate(MSGS, 1):
        assert len(m) < 4000, (i, len(m))
        if "--send" in sys.argv:
            send(m); print(f"::notice::전송 {i}/{len(MSGS)} 완료"); time.sleep(1)
        else:
            print("::notice::" + m.replace("%", "%25").replace("\n", "%0A"))


if __name__ == "__main__":
    main()
