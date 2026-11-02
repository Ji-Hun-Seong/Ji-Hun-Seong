#!/usr/bin/env bash
# 대시보드 설치: Tailscale(내 기기끼리만 연결되는 비공개 네트워크) + 상시 실행 서비스
# 서버에서 한 번: bash ~/ji-hun-seong/toss-bot/setup/dashboard.sh
set -e
cd ~/ji-hun-seong/toss-bot
curl -sL https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js -o static/chart.umd.min.js || true
command -v tailscale >/dev/null || curl -fsSL https://tailscale.com/install.sh | sh
sudo iptables -C INPUT -i tailscale0 -j ACCEPT 2>/dev/null || sudo iptables -I INPUT 1 -i tailscale0 -j ACCEPT
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y iptables-persistent >/dev/null && sudo netfilter-persistent save >/dev/null
sudo cp setup/toss-dash.service /etc/systemd/system/toss-dash.service
sudo systemctl daemon-reload && sudo systemctl enable --now toss-dash && sudo systemctl restart toss-dash
echo
echo "▶ 아래에 나오는 로그인 링크를 폰이나 PC 브라우저로 열어 Tailscale 계정(구글 로그인 가능)으로 승인하세요."
sudo tailscale up --hostname=toss-bot
IP=$(tailscale ip -4 | head -1)
echo
echo "✅ 대시보드 주소: http://$IP:8080   (또는 http://toss-bot:8080)"
echo "   폰에 Tailscale 앱을 설치하고 같은 계정으로 로그인한 뒤 위 주소를 열면 됩니다."
