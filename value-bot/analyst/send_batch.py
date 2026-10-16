"""send_batch.py — 애널리스트 노트를 하루 1묶음(5종목)씩 그룹방에 보낸다.

장중 공시 알림 워크플로(평일 5분마다)에서 매번 호출된다.
한국시간 09:00 이후 첫 실행에서, 오늘 아직 안 보냈고 남은 묶음이 있으면 다음 묶음을 보낸다.
GROUPS 환경변수(쉼표 구분)의 각 대화방으로 보낸다. 상태는 batch_state.json.
"""
import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "signal-bot"))
from daily_signals import send  # noqa: E402

BATCHES = os.path.join(HERE, "batches_2026-10.json")
STATE = os.path.join(HERE, "batch_state.json")

now = datetime.now(ZoneInfo("Asia/Seoul"))
today = now.strftime("%Y-%m-%d")
state = json.load(open(STATE)) if os.path.exists(STATE) else {"next": 0, "sent": {}}
batches = json.load(open(BATCHES, encoding="utf-8"))

if "--force" not in sys.argv:
    if now.hour < 9 or today in state["sent"].values() or state["next"] >= len(batches):
        sys.exit(0)

i = state["next"]
groups = [g.strip() for g in os.environ.get("GROUPS", "").split(",") if g.strip()]
if not groups:
    sys.exit("::error::GROUPS 가 비어 있습니다.")
for g in groups:
    os.environ["TELEGRAM_CHAT_ID"] = g
    for m in batches[i]:
        send(m)
state["sent"][str(i + 1)] = today
state["next"] = i + 1
json.dump(state, open(STATE, "w"), ensure_ascii=False, indent=1)
print(f"애널리스트 노트 {i + 1}/{len(batches)} 묶음 전송 완료 ({len(groups)}개 방)")
