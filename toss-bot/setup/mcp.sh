#!/usr/bin/env bash
# 🔌 토스봇 MCP 서버 설치: 비밀 경로 만들기 → 상시 실행 서비스 → Tailscale Funnel 로 이 주소 하나만 인터넷에 열기
# 서버에서 한 번: bash ~/ji-hun-seong/toss-bot/setup/mcp.sh
set -e
cd ~/ji-hun-seong/toss-bot
touch .env && chmod 600 .env
if ! grep -q '^MCP_SECRET=' .env; then
  echo "MCP_SECRET=$(python3 -c 'import secrets;print(secrets.token_urlsafe(24))')" >> .env
  echo "▶ 비밀 경로(MCP_SECRET)를 새로 만들었어요"
fi
sudo cp setup/toss-mcp.service /etc/systemd/system/toss-mcp.service
sudo systemctl daemon-reload && sudo systemctl enable --now toss-mcp && sudo systemctl restart toss-mcp
sleep 2
systemctl is-active toss-mcp >/dev/null && echo "✅ MCP 서버 실행 중 (localhost:8765)" || { echo "❌ MCP 서버가 안 켜졌어요:"; sudo journalctl -u toss-mcp -n 20 --no-pager; exit 1; }
echo "▶ Tailscale Funnel 켜는 중 — 처음이면 '관리 페이지에서 Funnel 허용' 링크가 나와요. 링크를 열어 허용한 뒤 이 스크립트를 다시 실행하세요."
sudo tailscale funnel --bg 8765
HOST=$(tailscale status --json | python3 -c 'import sys,json;print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')
SECRET=$(grep '^MCP_SECRET=' .env | cut -d= -f2-)
echo
echo "✅ Claude 앱에 넣을 연결 주소 (남에게 보여 주지 마세요):"
echo "   https://$HOST/$SECRET/mcp"
echo
echo "   Claude 앱 → 설정 → 커넥터 → 커스텀 커넥터 추가 → 이름 '토스봇', 위 주소 붙여넣기"
