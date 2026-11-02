#!/usr/bin/env bash
# 종목 검색 차트 페이지 실행 (서버에서): bash ~/ji-hun-seong/toss-bot/chartpage/start.sh
set -e
cd "$(dirname "$0")"
fc-list 2>/dev/null | grep -qi nanum || { sudo apt-get update -qq && sudo apt-get install -y -qq fonts-nanum && rm -rf ~/.cache/matplotlib; }
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q flask pandas matplotlib requests
set -a; [ -f ../.env ] && . ../.env; set +a        # 토스봇 .env의 DART_API_KEY 등 사용
pkill -f "python chart_server.py" 2>/dev/null || true
nohup .venv/bin/python chart_server.py > chart.log 2>&1 &
sleep 4
tail -3 chart.log
echo
echo "✅ 실행됨 → 아이폰 Tailscale 켜고 사파리에서  http://100.104.210.126:8081"
