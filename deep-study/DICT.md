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
- [x] 코스피200 정기변경 (kospi200-periodic-rebalancing)
- [x] 유동주식비율 (free-float-ratio)
- [x] 패시브 펀드 (passive-index-fund)
- [x] MSCI 지수 정기변경 (msci-index-review)
- [x] 외국인 투자 여유분 (foreign-room)
- [x] S&P 500 편입 요건 (sp500-eligibility)
- [ ] 사이드카
- [ ] 서킷브레이커

### 증자·감자
- [x] 1차 발행가액·2차 발행가액·확정 발행가액 (issue-price-stages)
- [ ] 신주배정기준일
- [x] 제3자배정 유상증자 (third-party-allotment)
- [ ] 단수주
- [ ] 신주 상장일

### 배당
- [ ] 주식배당
- [ ] 분기배당·중간배당
- [x] 배당가능이익 (distributable-profit)
- [ ] 배당소득세와 금융소득종합과세
- [ ] 우선주

### 메자닌·자금조달
- [x] 콜옵션(매도청구권)과 풋옵션(조기상환청구권) (cb-call-put-option)
- [ ] 상환전환우선주(RCPS)
- [ ] 회사채와 신용등급

### 공시·지배구조
- [x] 자기주식 취득 신탁계약 (buyback-trust)
- [x] 자기주식 소각 의무 (treasury-stock-mandatory-cancellation)
- [x] 기술특례상장 (tech-special-listing)
- [x] 추정 실적 괴리율 (forecast-deviation-rate)
- [x] 환매청구권(풋백옵션) (ipo-putback-option)
- [x] 사업보고서 (business-report)
- [x] 감사의견 (audit-opinion)
- [x] 주요사항보고서 (material-event-report)
- [x] 잠정실적 공시 (preliminary-earnings)
- [x] 이익발표 후 표류 (post-earnings-announcement-drift)
- [x] 표준화 기대외이익 (standardized-unexpected-earnings)
- [x] 실적 가이던스 (earnings-guidance)
- [x] 회계감리 (accounting-review)
- [x] 최대주주와 특수관계인 (largest-shareholder-related-party)
- [x] 대규모내부거래 (large-scale-internal-transaction)
- [x] 동반매도청구권 (drag-along-right)
- [x] 5% 룰(대량보유 보고) (five-percent-rule)
- [x] 임원·주요주주 소유상황 보고 (insider-ownership-report)
- [x] 내부자거래 사전공시 (insider-trading-plan-disclosure)
- [ ] 단기매매차익 반환
- [x] 지주회사 (holding-company)
- [x] 상장폐지·관리종목 (delisting-administrative-issue)
- [ ] 투자주의·경고·위험 종목
- [x] 거래정지 (trading-halt)
- [x] 기업가치 제고 계획 (corporate-value-up-plan)
- [x] 조회공시 (inquiry-disclosure)
- [x] 공정공시 (fair-disclosure)
- [x] 불성실공시법인 (unfaithful-disclosure-corporation)
- [x] 합병가액 (merger-valuation)
- [x] 합병 차익거래 (merger-arbitrage)
- [x] 합병 외부평가 (merger-external-valuation)
- [x] 분할비율 (split-ratio)
- [x] 재상장·변경상장 (relisting-change-listing)
- [x] 중복상장 (duplicate-listing)
- [x] 안분비례 (tender-offer-proration)
- [x] 대항공개매수 (competing-tender-offer)
- [x] 의무공개매수 (mandatory-tender-offer)

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
- [x] 자본잠식 (capital-impairment)
- [x] 분식회계 (accounting-fraud)
- [x] M-스코어 (beneish-m-score)
- [x] 영업권 (goodwill)
- [x] 손상차손 (impairment-loss)
- [x] 재고자산평가손실 (inventory-write-down)
- [x] 순차입금 (net-debt)
- [x] 리스부채 (lease-liability)
- [x] 감가상각비 (depreciation-amortization)
- [x] 클린서플러스 (clean-surplus)
- [x] 기타포괄손익 (other-comprehensive-income)
- [x] 이자보상배율 (interest-coverage-ratio)
- [x] 알트만 Z-스코어 (altman-z-score)
- [x] 주식보상비용 (stock-based-compensation)
- [x] 런웨이 (cash-runway)

### 가치 지표
- [x] PEG (peg)
- [x] 이익수익률 (earnings-yield)
- [x] PSR (psr)
- [ ] BPS
- [x] 컨센서스 (consensus)
- [x] 자기자본비용 (cost-of-equity)
- [x] 현금흐름할인법 (dcf)
- [x] 터미널 가치 (terminal-value)
- [x] 가중평균자본비용 (wacc)
- [x] 베타 (beta)
- [x] 시장위험프리미엄 (equity-risk-premium)
- [x] CAPM (capm)
- [x] F-스코어 (piotroski-f-score)
- [x] 잔여이익 (residual-income)
- [x] 지주회사 할인 (holding-company-discount)
- [x] SOTP (sotp)
- [x] 정상 이익 (normalized-earnings)
- [x] 경기조정 PER (cape-ratio)
- [x] 영업레버리지 (operating-leverage)
- [x] 가치함정 (value-trap)

### 금융주
- [x] 보통주자본비율 (cet1-ratio)
- [x] 위험가중자산 (risk-weighted-assets)
- [x] 완충자본 (capital-buffer)
- [x] 지급여력비율(K-ICS) (kics-ratio)
- [x] 보험계약마진(CSM) (contractual-service-margin)
- [x] 해약환급금준비금 (surrender-reserve)
- [x] 순자본비율(NCR) (net-capital-ratio)
- [x] 여전사 레버리지 규제 (credit-finance-leverage-limit)
- [x] 종합금융투자사업자(종투사) (comprehensive-investment-bank)
- [ ] 순이자마진(NIM)
- [ ] 대손비용률
- [ ] 신종자본증권(조건부자본증권)

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
- [x] 지방채 (local-government-bond)
- [x] 지역개발채권 (regional-development-bond)
- [x] 특수채 (special-bond)
- [x] 지방공사채 (local-public-corporation-bond)
- [x] 은행채 (bank-bond)
- [x] KOFR(무위험 지표금리) (kofr)
- [x] 여전채 (yeojeon-bond)
- [x] 레버리지 배율(여전사) (credit-finance-leverage)
- [x] 금융지주채 (financial-holding-bond)
- [x] 이중레버리지비율 (double-leverage-ratio)
- [x] 회사채 수요예측 (bond-book-building)
- [x] 증권신고서 효력발생일 (registration-effective-date)
- [x] 관계인수인 거래 (related-underwriter)
- [x] 불성실 수요예측 참여자 (unfaithful-bookbuilding)
- [x] 자산유동화증권(ABS) (abs)
- [x] 유동화 신용보강·조기상환 트리거 (securitization-credit-enhancement)
- [x] 주택저당증권(MBS) (mbs)
- [x] 조기상환율(CPR·SMM·PSA) (prepayment-rate-cpr-psa)
- [x] 이중상환청구권부채권(커버드본드) (covered-bond)
- [x] 기초자산집합(커버풀)·최소담보비율 (cover-pool)
- [x] 채권 동시결제(DVP) (bond-dvp-settlement)
- [x] 장외채권 거래 보고(15분 보고) (otc-bond-trade-report)
- [x] 결제 실패(결제 지연·불이행) (settlement-fail)
- [x] 체결가 괴리(민평 괴리) 점검 (trade-price-deviation)
- [x] 채권 보유기간 과세(보유기간이자상당액) (holding-period-interest-tax)
- [x] 세후수익률·세전환산수익률 (after-tax-yield)
- [x] 단수기간(단리할인 구간) (odd-period-discount)
- [x] Act/Act(ICMA)·ISDA·AFB (act-act-icma)
- [x] 채권 이자 기준일 (bond-record-date)
- [x] 국채전문유통시장(KTS) (ktb-specialized-market)
- [x] 유효이자율법 (effective-interest-method)
- [x] 이자수익·평가손익 구분 (interest-valuation-split)
- [x] 금리 결정일 (rate-fixing-date)
- [x] 룩백·관찰기간 이동 (lookback-observation-shift)
- [x] 후순위채 (subordinated-bond)
- [x] 지급여력비율(K-ICS) (kics-ratio)
- [x] 보험사 자본성증권(기본자본·보완자본) (insurer-capital-securities)
- [x] 물가연동계수 (inflation-index-ratio)
- [x] 손익분기 인플레이션(BEI) (breakeven-inflation)
- [x] 민평 평균 방식(평가사 수·평균 순서) (pricing-agency-average)
- [x] 평가사 간 괴리 (pricing-agency-divergence)
- [x] 채권 손익 요인분해 (bond-pnl-attribution)
- [x] 유효듀레이션·음의 컨벡시티 (effective-duration)
- [x] 등급전망·등급감시 (rating-outlook-watch)
- [x] 등급 하락 자산 처리 (downgraded-asset-handling)
- [x] 부도채권 분류·상각 (distressed-bond-writedown)
- [x] 회생채권 (rehabilitation-claim)
- [x] 출자전환 (debt-equity-swap)
- [x] 회생계획 인가·권리변경 (rehabilitation-plan-confirmation)

### 펀드 기본·구조
- [x] 설정조정금·환매조정금 (adjustment-account)
- [x] 원본 (fund-principal)
- [x] 집합투자규약 (fund-bylaws)
- [x] 투자신탁과 투자회사 (investment-trust-company)
- [x] 환매연기 (redemption-deferral)
- [x] 수익자총회 (beneficiaries-meeting)
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
