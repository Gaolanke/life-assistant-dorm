#!/usr/bin/env bash
# 确认从没发过「填报提醒」，并看测试是否碰到真实群
set -u
cd /www/dorm || exit 1
export DORM_DATA_DIR=/www/dorm-data

.venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from sqlalchemy import select
from backend.database import SessionLocal
from backend.models import PushLog

db = SessionLocal()
rows = db.execute(select(PushLog).where(PushLog.scene == "fill_remind")).scalars().all()
print(f"  fill_remind（填报提醒）推送记录: {len(rows)} 条")
for r in rows:
    print(f"    {r.created_at} {r.status} {r.detail}")

print()
print("  当前推送目标群:")
from backend.services import settings_service as ss
print(f"    qqbot_groups = {ss.get_setting(db, 'qqbot_groups')!r}")
print(f"    qqbot_enabled = {ss.get_setting(db, 'qqbot_enabled')!r}")
db.close()
PY
