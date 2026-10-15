"""resend.py — 마지막으로 보낸 일일 신호(last_messages.json, 3통)를 다른 대화방(TELEGRAM_CHAT_ID)으로 다시 보낸다."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from daily_signals import send  # noqa: E402

path = os.path.join(HERE, "last_messages.json")
if not os.path.exists(path):
    sys.exit("::error::last_messages.json 이 없습니다.")
for m in json.load(open(path, encoding="utf-8")):
    send(m)
