#!/usr/bin/env bash
# 修正被写坏的时间设置，并确认定时任务时间正确
set -u
cd /www/dorm || exit 1
export DORM_DATA_DIR=/www/dorm-data

.venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from sqlalchemy import select
from backend import scheduler
from backend.database import SessionLocal
from backend.models import Setting
from backend.services import settings_service as ss

db = SessionLocal()

print("=== 修正前 ===")
for k in ("qq_report_time", "report_deadline", "auto_export_time", "auto_backup_time"):
    row = db.execute(select(Setting).where(Setting.key == k)).scalar()
    print(f"  {k:<22} = {row.value!r}" if row else f"  {k:<22} = (缺)")

# 按最初约定修正：截止 22:00，汇报 22:40
fix = {
    "report_deadline": "22:00",
    "qq_report_time": "22:40",
}
ss.update_settings(db, fix)

print()
print("=== 修正后 ===")
for k in ("qq_report_time", "report_deadline", "auto_export_time", "auto_backup_time"):
    row = db.execute(select(Setting).where(Setting.key == k)).scalar()
    print(f"  {k:<22} = {row.value!r}" if row else f"  {k:<22} = (缺)")
db.close()

print()
print("=== 定时任务（重启后生效）===")
for j in scheduler.build_scheduler().get_jobs():
    print(f"  {j.id:<18} {j.trigger}")
PY
