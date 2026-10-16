#!/usr/bin/env bash
# 查看时间类设置与定时任务
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

db = SessionLocal()
print("时间类设置：")
for k in (
    "qq_report_time",
    "report_deadline",
    "showdoc_remind_time",
    "auto_export_time",
    "auto_backup_time",
):
    row = db.execute(select(Setting).where(Setting.key == k)).scalar()
    print(f"  {k:<22} = {row.value!r}" if row else f"  {k:<22} = (缺)")
db.close()

print()
print("对应定时任务：")
for j in scheduler.build_scheduler().get_jobs():
    print(f"  {j.id:<18} {j.trigger}")
PY
