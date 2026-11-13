# 백과사전 (마스터로드)

앱의 '백과' 탭. 용어를 치면 그 항목으로 바로 들어가고, 레슨·심화 글 본문의 용어에는 자동 밑줄 링크가 걸린다.
엔진은 `toss-bot/static/dict.js`(펀드로드에도 붙일 수 있게 공용), 항목은 `toss-bot/static/masterroad/dict/src/<id>.json` 한 파일에 하나.

- 검사·합치기: `python deep-study/dict_build.py` → `dict/terms.json` 생성 (실패하면 올리지 않는다)
- 새 항목은 아래 '써야 할 항목'의 맨 위 `[ ]`부터 쓰고 `[x]`로 바꾼다. 쓰다가 필요한 용어가 생기면 목록에 추가한다.

## 항목 형식

```json
{"id":"ex-dividend-date","k":"배당락일","en":"Ex-dividend date","area":"배당",
 "al":["배당락","배당부"],            // 검색 + 본문 자동 링크에 쓰는 다른 이름
 "al2":["ex-date"],                   // 검색에만 쓰는 이름(흔한 단어라 링크하면 시끄러운 것)
 "one":"한두 문장 정의 — 검색 결과에 그대로 보인다",
 "sec":[{"h":"한마디로","b":[{"p":"문단"}]}, ...],   // 블록은 심화 글과 같다: p ul tip calc table f j
 "rel":["배당기준일","결제일"],       // 이미 있는 항목의 이름만
 "src":[{"t":"문서","u":"https://...","o":"기관"}],
 "upd":"2026-11-10"}
```

## 화면 모양 (인포그래픽 먼저, 글은 그다음)

첫 절은 반드시 `"h":"한눈에 보기"` 이고 `hero` 블록으로 시작한다. 그 아래에 `pts`·`tl`·`branch`·`kv`·`donut`·`pc`·`callout` 중 맞는 것을 2개 이상 쓴다. 긴 3열 표는 폰에서 읽기 어려우니 일정은 `tl`, 비교는 `branch`·`pc`, 숫자 요약은 `kv` 로 바꾼다. 참고 항목: fundroad `rights-offering-fund.json`, `ktb-lifecycle.json`, masterroad `rights-offering.json`.

```json
{"hero":{"kicker":"실제 사례 · 회사 연도","title":"짧은 제목","sub":"한 줄 요약","stats":[["라벨","값"]]}}
{"pts":[{"i":"coin","t":"제목","x":"설명"}]}                    // 핵심 포인트 카드
{"tl":[{"i":"cal","d":"9.04","t":"일정","x":"설명","me":"펀드회계가 할 일"}]}  // 아이콘 타임라인
{"branch":[{"t":"선택지","i":"check","tone":"acc|blue|gold|bad","x":"설명","r":"결과"}]}
{"kv":[["항목","값"]]}   {"donut":{"center":"합계","total":"8,861억","items":[["용도",7650,"7,650억"]]}}
{"pc":{"badT":"단기 부담","bad":["..."],"goodT":"중장기 기대","good":["..."]}}   {"callout":"한 줄 핵심"}
```
그림 블록(쉬운 설명용, 한눈에 보기 안에 1개 이상 권장):
```json
{"ex":{"title":"유상증자란 무엇일까?","l":{"a":"company","t":"기업"},"r":{"a":"investors","t":"투자자"},"top":{"t":"새로운 주식 발행","a":"stock"},"bot":{"t":"자금 확보","a":"money"},"note":"한두 줄 설명"}}
{"chain":{"title":"흐름 제목","nodes":[{"a":"fund","t":"단계","x":"설명","go":"다음 단계로 가는 화살표 글"}]}}
```
토스풍 흐름 그림(권리·전환처럼 "A → 값 → B, 그리고 고르기"인 개념에):
```json
{"flow":{"title":"신주인수권","en":"(Right)","sub":["한 줄","한 줄"],"items":[{"a":"warrant","t":"증서"},{"a":"coindown","t":"발행가 납입"},{"a":"newstock","t":"신주 받기"}],"or":[{"t":"청약","s":"설명"},{"t":"매도","s":"설명"}],"badge":"기한 내에 선택!"}}
```
그림 이름: coindown newstock warrant hourglass company investors person stock bond money coin bank gov fund factory doc cal chartup ticket building. 액터 이름표는 6자 이내로 짧게.

아이콘 이름: users doc coin mega bank up down cal target flag alert check cash building clock bond pct swap key calc bulb x

## 쓰는 기준 (A부터 Z까지)

- 절 순서 권장: 한마디로 → 왜 있나/원리 → 절차·일정 → 계산식 → 숫자 예시(끝까지 계산, 가정 표시) → 주가·투자자 영향 → 헷갈리는 말 비교(표) → 실수·체크리스트.
- 제도 수치·날짜는 이번에 원문으로 확인한 것만 쓰고 src 에 단다. 확인 못 하면 쓰지 않는다. 원문 문장은 베끼지 않는다.
- 이름(k·al·al2·en)은 다른 항목과 겹치면 검사에서 막힌다. 두 글자 흔한 단어는 al2 로.
- 계산은 python 으로 검산한다.

## 써야 할 항목

### 시장 구조·파생
- [x] 프로그램매매 (program-trading)
- [x] 베이시스 (basis)
- [x] 선물옵션 동시만기일 (expiry-day)
- [x] 업틱룰 (uptick-rule)
- [x] 공매도 과열종목 (short-selling-overheated)
- [x] 공매도 잔고 공시 (short-position-disclosure)
- [x] 신용거래융자 (margin-loan)
- [x] 미수거래 (unsettled-purchase)
- [x] 담보유지비율 (maintenance-ratio)
- [x] 투자자별 매매동향 (investor-flow)
- [x] 외국인 보유비중 (foreign-ownership)
- [x] 기관계 (institution-type)
- [x] 대체거래소 (alternative-trading-system)
- [x] 최선집행의무 (best-execution)
- [x] 애프터마켓 (after-market)
- [x] 다크풀 (dark-pool)
- [x] NBBO·주문보호규칙 (nbbo)
- [x] 주문흐름 대가 PFOF (payment-for-order-flow)
- [x] 미결제약정 (open-interest)
- [x] 델타 헤지 (delta-hedging)
- [x] 풋콜비율 (put-call-ratio)
- [ ] 사이드카
- [ ] 서킷브레이커

### 증자·감자
- [ ] 1차 발행가액·2차 발행가액·확정 발행가액 (별도 항목으로 깊게)
- [ ] 신주배정기준일
- [ ] 제3자배정 유상증자
- [ ] 단수주
- [ ] 신주 상장일

### 배당
- [ ] 주식배당
- [ ] 분기배당·중간배당
- [ ] 배당소득세와 금융소득종합과세
- [ ] 우선주

### 메자닌·자금조달
- [ ] 콜옵션(매도청구권)과 풋옵션(조기상환청구권)
- [ ] 상환전환우선주(RCPS)
- [ ] 회사채와 신용등급

### 공시·지배구조
- [x] 사업보고서 (business-report)
- [x] 감사의견 (audit-opinion)
- [x] 주요사항보고서 (material-event-report)
- [x] 잠정실적 공시 (preliminary-earnings)
- [ ] 최대주주와 특수관계인
- [ ] 5% 룰(대량보유 보고)
- [ ] 지주회사
- [ ] 상장폐지·관리종목
- [ ] 투자주의·경고·위험 종목
- [ ] 거래정지

### 재무제표
- [x] 영업이익 (operating-profit)
- [x] 당기순이익과 지배주주 순이익 (net-income-controlling)
- [x] 부채비율 (debt-ratio)
- [x] 운전자본 (working-capital)
- [x] 충당부채와 우발부채 (provision-contingent-liability)
- [x] 영업활동현금흐름 (operating-cash-flow)
- [x] 잉여현금흐름(FCF) (free-cash-flow)
- [x] 발생액 (accruals)
- [x] 연결재무제표 (consolidated-financial-statements)
- [x] 비지배지분 (non-controlling-interest)
- [x] 지분법 (equity-method)
- [ ] 자본잠식
- [x] 영업권 (goodwill)
- [x] 손상차손 (impairment-loss)
- [x] 재고자산평가손실 (inventory-write-down)

### 가치 지표
- [ ] PEG
- [ ] PSR
- [ ] BPS
- [ ] 컨센서스

### 거래 제도
- [ ] 호가단위
- [ ] 동시호가(단일가매매)
- [ ] 시간외 거래
- [ ] 서킷브레이커·사이드카
- [ ] 대체거래소(NXT)
- [ ] 프로그램매매
- [ ] 선물옵션 만기일
- [ ] 수급(외국인·기관·개인)
- [ ] 거래대금과 회전율

### 차트·지표 (기초 레슨과 연결)
- [ ] 이동평균선
- [ ] 골든크로스·데드크로스
- [ ] RSI
- [ ] MACD
- [ ] 볼린저밴드
- [ ] 거래량
- [ ] 지지선·저항선
- [ ] 갭
- [ ] 캔들

---

# 펀드로드 백과

항목은 `toss-bot/static/fundroad/dict/src/<id>.json`. 형식·기준은 위와 같고, 분개(`j` 블록, 대차 일치)를 적극 쓴다. 분야(area): 펀드 기본 / 펀드 구조 / 채권·단기자금 / 주식 기업행위 / 파생·외화 / 대체자산 / 결산·세무 / 법규·통제.

## 펀드로드 써야 할 항목

### 채권·단기자금
- [x] FRN(변동금리채)
- [x] 물가연동국고채
- [x] 콜옵션부 채권·신종자본증권 (callable-hybrid)
- [x] 사채관리회사 (bond-trustee)
- [x] 신용등급과 신용스프레드
- [x] 기한이익상실
- [x] 사이드포켓 (side-pocket)
- [x] 영업일 조정 관행 (business-day-convention)
- [x] 채권 대차 (bond-lending)
- [x] 국고채 지표물·경과물
- [x] 현물금리·선도금리 (spot-forward-rate)
- [x] 단리·복리 (simple-compound)
- [x] 연속복리 (continuous-compounding)
- [x] 불규칙 이표(전기·후기 이자) (odd-coupon)
- [x] 말일 규칙(EOM) (eom-rule)
- [x] 휴일이자(만기 휴일) (holiday-interest)
- [x] 보유기간수익률 (holding-period-return)
- [x] 실효수익률 (realized-compound-yield)
- [x] 수익률 곡선 (yield-curve)
- [x] 재투자 위험 (reinvestment-risk)
- [x] 할인계수 (discount-factor)
- [x] 액면수익률 (par-yield)
- [x] Z스프레드 (z-spread)
- [x] 할인 마진(DM) (discount-margin)
- [x] 국고채 스트립(원금이자분리채권) (ktb-strips)
- [x] 국고채 통합발행 (ktb-fungible-issue)
- [x] 통화안정증권 (msb)
- [x] 재정증권 (treasury-bill-kr)
- [x] 국민주택채권 (national-housing-bond)
- [x] 소액채권시장 (small-bond-market)

### 펀드 기본·구조
- [x] 설정조정금·환매조정금 (adjustment-account)
- [ ] 원본
- [ ] 집합투자규약
- [ ] 투자신탁과 투자회사
- [ ] 수탁회사·일반사무관리회사
- [ ] 개방형·폐쇄형·환매금지형
- [ ] 단위형·추가형
- [ ] 공모펀드·사모펀드
- [ ] ETF와 PDF
- [ ] TDF
- [ ] MMF와 장부가 평가
- [ ] 성과보수와 하이워터마크
- [ ] 판매수수료(선취·후취)
- [ ] 환매수수료
- [ ] 기준가 오류와 투자자 보전
- [ ] 평가위원회

### 주식 기업행위(펀드 처리)
- [ ] 미수배당금
- [x] 신주인수권 평가(펀드) (rights-offering-fund)
- [ ] 권리 통지(예탁결제원)
- [ ] 합병·분할 장부 승계

### 파생·외화
- [ ] 선물 일일정산
- [ ] 옵션 프리미엄과 행사
- [ ] 이자율스왑(IRS)
- [ ] 통화스왑(CRS)
- [ ] 선물환·NDF
- [ ] 위험평가액
- [ ] 적용 환율과 외화환산
- [ ] 환헤지 클래스

### 대체자산
- [ ] 임대보증금
- [ ] 마스터리스·책임임차
- [ ] WALE와 공실률
- [ ] 인수금융
- [ ] 리츠
- [ ] 개발형 펀드의 건설중인자산
- [ ] 이자유보금
- [ ] 책임준공
- [ ] 블라인드 펀드
- [ ] 세컨더리
- [ ] 클로백
- [ ] NPL
- [ ] 선박·항공기 잔존가치

### 결산·세무·통제
- [ ] 분배 가능 이익과 유보
- [ ] 비과세 손익 범위
- [ ] 배당소득 원천징수(펀드 환매·분배)
- [ ] 외국납부세액
- [ ] 자산운용보고서
- [ ] 수탁 대사
- [ ] 메이커·체커
