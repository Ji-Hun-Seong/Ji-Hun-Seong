#!/usr/bin/env bash
# 🔄 자동 반영 — GitHub에 올라온 새 코드를 서버가 스스로 받아서 필요한 서비스만 재시작
#   cron 이 2분마다 실행 (crontab.txt). 바뀐 게 없으면 아무것도 안 함.
#   · 화면 파일(static/)만 바뀜     → 받기만 (앱 새로고침하면 반영)
#   · dashboard·chartpage(.py) 바뀜 → toss-dash 재시작
#   · mcp_server.py 바뀜            → toss-mcp 재시작
#   · scanner.py 바뀜               → toss-scan 재시작
#   · setup/crontab.txt 바뀜        → 일정 다시 등록
#   기록: state/deploy.log
set -u
REPO="$HOME/ji-hun-seong"
LOG="$REPO/toss-bot/state/deploy.log"
mkdir -p "$REPO/toss-bot/state"
exec 9>/tmp/toss-auto-deploy.lock
flock -n 9 || exit 0                                    # 앞 실행이 아직 돌고 있으면 건너뜀

cd "$REPO" || exit 1
git fetch -q origin main 2>>"$LOG" || exit 0
OLD=$(git rev-parse HEAD)
NEW=$(git rev-parse origin/main)
[ "$OLD" = "$NEW" ] && exit 0

ts() { date '+%F %T'; }
if ! git merge -q --ff-only origin/main 2>>"$LOG"; then
  echo "$(ts) ⚠️ 받기 실패(서버에 직접 고친 파일이 있음) — git status 확인 필요" >>"$LOG"
  git status --short >>"$LOG" 2>&1
  exit 1
fi
CH=$(git diff --name-only "$OLD" "$NEW" -- toss-bot)
[ -z "$CH" ] && exit 0                                  # 급등 연구 데이터 등 다른 폴더만 바뀜
echo "$(ts) ⬇️ ${OLD:0:7} → ${NEW:0:7}: $(echo "$CH" | wc -l)개 파일" >>"$LOG"

restart() { sudo -n systemctl restart "$1" 2>>"$LOG" && echo "$(ts)   ↻ $1 재시작" >>"$LOG" || echo "$(ts)   ⚠️ $1 재시작 실패" >>"$LOG"; }
echo "$CH" | grep -qE '^toss-bot/[^/]*\.py$|^toss-bot/chartpage/.*\.py$' && restart toss-dash
echo "$CH" | grep -q '^toss-bot/mcp_server\.py$' && restart toss-mcp
echo "$CH" | grep -qE '^toss-bot/scanner\.py$' && systemctl list-unit-files toss-scan.service >/dev/null 2>&1 && restart toss-scan
if echo "$CH" | grep -q '^toss-bot/setup/crontab\.txt$'; then
  crontab "$REPO/toss-bot/setup/crontab.txt" && echo "$(ts)   🗓 일정 다시 등록" >>"$LOG"
fi
exit 0
