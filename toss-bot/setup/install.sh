#!/usr/bin/env bash
# Oracle Cloud(Ubuntu 22.04/24.04) 서버에서 한 번 실행: bash install.sh
set -e
sudo timedatectl set-timezone Asia/Seoul
sudo apt-get update -y && sudo apt-get install -y python3-venv git
cd $HOME
[ -d ji-hun-seong ] || git clone https://github.com/Ji-Hun-Seong/Ji-Hun-Seong.git ji-hun-seong
cd ji-hun-seong && git pull -q
cd toss-bot
python3 -m venv .venv
.venv/bin/pip install -q requests pandas numpy
[ -f .env ] || { cp .env.example .env; chmod 600 .env; }
mkdir -p state
echo
echo "서버 공인 IP: $(curl -s https://api.ipify.org)   ← 토스증권 WTS > 설정 > Open API > 허용 IP에 등록"
echo "다음: nano .env 로 키 입력 → .venv/bin/python bot.py test → crontab setup/crontab.txt"
