# 토스증권 스윙 자동매매 봇 (코스피 · 일봉)

RSI · 볼린저밴드 · 피보나치 · 거래량으로 신호를 내고, 다음 날 아침 **장 시작 동시호가(시가)** 로 주문합니다.
토스증권 Open API는 **등록한 IP에서만** 호출되므로 고정 IP 서버(Oracle Cloud 무료)에서 돌립니다. GitHub Actions에서는 안 됩니다.

## 매매 규칙 (`strategy.py`)
| | 조건 |
|---|---|
| 시장 | KOSPI 종가 > 200일선일 때만 신규 매수 |
| 볼린저 | 최근 10일 안에 밴드폭이 1년 중 하위 20%(스퀴즈) → 오늘 종가가 상단(20일, 2σ) 돌파 |
| 피보나치 | 종가가 직전 60일 고점(되돌림 100%) 돌파 |
| RSI | RSI14 > 60 매수 / RSI14 < 40 이면 다음 날 시가 매도 |
| 거래량 | 오늘 거래량 ≥ 20일 평균 |
| 추세·유니버스 | 50일선 > 200일선, 20일 평균 거래대금 상위 200 (상장 1년 이상), 6개월 모멘텀 순 최대 10종목 |

백테스트(2015-11~2026-10, 비용 반영, 시점별 유니버스): 연 20.0%, MDD -40%, 평균 투자비중 53% / 코스피200 연 13.9%, MDD -41%.
2015~2020 구간은 지수보다 낮았고(7.4% vs 8.9%), 주변 파라미터 중앙값은 연 14.7% → **기대치는 '지수 비슷한 수익, 투자비중 절반'**.
피보나치 되돌림 눌림목 매수(38.2~61.8%)는 108개 조합 모두 손실이어서 쓰지 않습니다. 근거: `backtest/research/README.md` 5차.

## 하루 일정 (서버 시간 KST, 휴장일 자동 건너뜀)
- 08:45 `bot.py open` — 전날 계획대로 시가 주문 (가상 모드면 기록만)
- 09:10 `bot.py confirm` — 체결 확인, 장부 반영, 텔레그램 보고
- 15:45 `bot.py evening` — 일봉 갱신 → 신호 → 내일 계획 → 텔레그램 보고

## 안전장치
- 봇 장부에 있는 종목·수량만 매도 — 계좌의 다른 보유 주식은 건드리지 않음
- `BOT_CAPITAL`(총액), `MAX_ORDER_KRW`(종목당), `MAX_NEW_BUYS`(하루 신규) 한도
- 투자경고·위험·단기과열·정리매매 종목 매수 제외
- 주문마다 `clientOrderId` 멱등키 → 재시도해도 중복 주문 없음, 동시 실행 잠금
- 긴급 정지: 서버에서 `touch ~/ji-hun-seong/toss-bot/STOP` (해제는 `rm STOP`)
- 처음엔 `paper`(가상) 모드. 2주 뒤 결과를 보고 `python bot.py mode live` 로 직접 전환

## 설치 (처음 한 번, PC에서 30분 정도)
1. **Oracle Cloud 가입** — cloud.oracle.com, 홈 리전 *South Korea Central (Seoul)* 또는 *Chuncheon*. 카드 인증만 하고 Always Free 범위는 과금 없음.
   - 무료 계정은 CPU를 거의 안 쓰는 서버를 회수할 수 있음 → 오래 쓰려면 *Pay As You Go* 로 업그레이드(무료 범위 내 사용 시 0원)
2. **서버 만들기** — Compute → Instances → Create: 이미지 *Ubuntu 24.04*, Shape *VM.Standard.E2.1.Micro*(Always Free).
   SSH 키 *Save private key* 로 내려받기. 만든 뒤 Networking에서 공인 IP를 **Reserved Public IP** 로 바꾸기(재시작해도 IP 유지).
3. **접속** — PC 터미널(윈도우는 PowerShell): `ssh -i 내려받은키.key ubuntu@서버IP`
4. **설치** — `curl -sL https://raw.githubusercontent.com/Ji-Hun-Seong/Ji-Hun-Seong/main/toss-bot/setup/install.sh | bash`
   → 마지막에 서버 공인 IP 출력
5. **토스증권 키** — PC 웹(WTS) 로그인 → 설정 → Open API → `client_id`/`client_secret` 발급, **허용 IP 관리**에 4번의 IP 등록
6. **설정** — `cd ~/ji-hun-seong/toss-bot && nano .env` 에 키, 텔레그램 토큰·개인 chat id, 운용 한도 입력 (Ctrl+O 저장, Ctrl+X 종료)
7. **점검** — `.venv/bin/python bot.py test` → 텔레그램에 "연결 테스트 성공"
8. **첫 신호 계산(선택)** — `.venv/bin/python bot.py evening` (첫 실행은 800종목 일봉을 받느라 2~3분)
9. **자동 실행 등록** — `crontab setup/crontab.txt`

업데이트: `cd ~/ji-hun-seong && git pull` · 상태: `.venv/bin/python bot.py status` · 로그: `state/bot.log`
