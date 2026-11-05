#!/usr/bin/env bash
# 급등주 장중 스냅샷(GitHub Actions surge-intraday.yml)을 서버 cron 으로 깨운다.
# GitHub 자체 예약 실행은 바쁠 때 통째로 빠져서(11/3~5 하루 1~3번만 실행) 서버가 대신 시각을 지킨다.
# 필요: toss-bot/.env 에 GH_TOKEN (Fine-grained 토큰 · 이 저장소만 · Actions: Read and write)
cd "$(dirname "$0")/.." || exit 1
GH_TOKEN=$(grep -E '^GH_TOKEN=' .env 2>/dev/null | cut -d= -f2-)
[ -z "$GH_TOKEN" ] && { echo "$(date '+%F %T') GH_TOKEN 없음"; exit 1; }
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST \
  -H "Authorization: Bearer $GH_TOKEN" -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/Ji-Hun-Seong/Ji-Hun-Seong/actions/workflows/surge-intraday.yml/dispatches \
  -d '{"ref":"main"}')
echo "$(date '+%F %T') surge-intraday 실행 요청 → HTTP $code (204 = 성공)"
