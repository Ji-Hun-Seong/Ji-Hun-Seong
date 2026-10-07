# Value DNA bot (@KoreaValueStock_Bot)

매매일지에서 뽑은 투자 성향(`profile.json`, 금액 없음)과 후보 종목 지표(`universe.csv`)로
코스피 가치주 20선을 점수화해 매월 1일 오전 9시(KST) 텔레그램으로 보냅니다.

- 워크플로: `.github/workflows/value-bot.yml` (Actions 탭 → Value DNA picks → Run workflow 로 시험 전송)
- 필요한 시크릿: `VALUE_TG_TOKEN`(새 봇 토큰), `VALUE_TG_CHAT_ID`(받을 그룹, 없으면 `TG_CHAT_ID`로 본인에게), 선택 `DART_API_KEY`
- 그룹 chat ID 찾기: 그룹에 봇 초대 → Actions → Value DNA picks → Run workflow에서 mode=find_chat
- 매매일지 원본은 공개 저장소에 올리지 않습니다. 성향을 다시 계산하려면 로컬에서
  `python recommend.py --journals 일지폴더 --export-profile profile.json` 후 `profile.json`만 커밋하세요.
