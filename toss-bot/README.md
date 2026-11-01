# 토스증권 자동매매 봇

토스증권 Open API는 **등록한 IP에서만** 호출되므로 고정 IP 서버(Oracle Cloud 무료, 도쿄 리전도 등록 가능 확인)에서 돌립니다.
처음엔 `paper`(가상) 모드 — 주문 없이 "냈을 주문"만 기록·보고. 결과를 보고 `bot.py mode live`로 직접 전환.

## 전략
**한국 — 자사주 공시 스윙** (근거: `backtest/research/README.md` 7차)
- 07:30~20:00 DART를 30초마다 확인 → 코스피 보통주의 자기주식 취득결정·신탁계약체결결정 원공시(정정 제외), 20일 평균 거래대금 3억 이상
- 장중(09:00~15:20): 바로 지정가 매수(현재가 +1.5%, 전일 종가 +5% 넘으면 안 삼), 3분 뒤 미체결분 취소
- 장 마감 후: 넥스트레이드 지원 종목은 애프터마켓에서, 아니면 다음 날 시가(전일 종가 +5% 상한)
- 10거래일 보유, RSI14 > 70이면 다음 날 시가 익절. 최대 10종목, 남는 돈은 현금
- 백테스트(2015-11~2026-10): 다음 날 시가 진입 연 13.6% · 손실 연도 없음 / 공시일 종가 진입(상한) 연 25.4%

**미국 — 나스닥 변동성 맞춤 레버리지** (근거: 6차)
- QQQ가 200일선 위면 레버리지 = min(2, 45% ÷ 최근 20일 변동성), 아래면 현금. TQQQ 비중 = 레버리지 ÷ 3
- 주 1회(미국 월요일 장중) 조정, 차이 5%p 이상일 때만
- 백테스트: 10년 연 24.0% vs 나스닥100 17.9%, 1990~ 19.9%(MDD -46%) vs 14.1%(MDD -83%)

## 일정 (서버 시간 KST, `setup/crontab.txt`)
| 시간 | 명령 | 하는 일 |
|---|---|---|
| 07:25~20:05 | `watch` | 공시 감시·즉시 매수 (꺼지면 10분마다 재시작) |
| 08:45 | `kr_open` | 매도 예정 + 밤사이 공시 종목 시가 주문 |
| 09:10 | `kr_confirm` | 시가 체결 확인 |
| 15:40 | `kr_close` | 보유일·RSI 확인 → 내일 매도 예정, 일일 보고 |
| 화·수 00:10 | `us_rebalance` | TQQQ 비중 조정 (주 1회) |

## 안전장치
- 봇 장부 종목·수량만 매도 — 계좌의 다른 주식은 건드리지 않음
- `KR_CAPITAL`, `KR_SLOTS`, `US_CAPITAL_USD` 한도 / 투자경고·과열·정리매매 제외 / 주문마다 멱등키
- 긴급 정지: `touch ~/ji-hun-seong/toss-bot/STOP` (해제 `rm STOP`)
- 공시 감지 기록 `state/detections.jsonl` — 감지 시각·가격으로 실제로 갭을 얼마나 잡는지 측정

## 설치·업데이트
```
curl -sL https://raw.githubusercontent.com/Ji-Hun-Seong/Ji-Hun-Seong/main/toss-bot/setup/install.sh | bash
cd ~/ji-hun-seong/toss-bot && nano .env          # 키 입력 (.env.example 참고)
.venv/bin/python bot.py test                     # 연결 점검
crontab setup/crontab.txt                        # 자동 실행 등록
```
업데이트: `cd ~/ji-hun-seong && git pull` · 상태: `.venv/bin/python bot.py status` · 로그: `state/bot.log`
