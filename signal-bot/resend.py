"""resend.py — 마지막으로 보낸 일일 신호(last_run.txt)를 다른 대화방(TELEGRAM_CHAT_ID)으로 다시 보낸다."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from daily_signals import send  # noqa: E402

text = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "last_run.txt"), encoding="utf-8").read()
start = text.find("📈")
end = text.find("텔레그램 전송 완료")
if start < 0:
    sys.exit("::error::last_run.txt 에 보낼 메시지가 없습니다.")
send(text[start:end if end > 0 else None].strip())
