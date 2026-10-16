#!/usr/bin/env bash
# 核对所有定时任务的时间设置（汇报必须为 22:40）
set -u
cd /www/dorm || exit 1

echo "=== 1. 应用内设置 ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.services import settings_service as ss

db = SessionLocal()
keys = [
    ('qq_report_time', '每晚群汇报时间'),
    ('report_deadline', '填报截止时间'),
    ('showdoc_remind_time', '未填报提醒时间'),
    ('auto_export_time', '自动导出 Excel 时间'),
]
for k, label in keys:
    print(f"  {label:<18} {k:<22} = {ss.get_setting(db, k)!r}")
db.close()
PY

echo
echo "=== 2. 定时任务调度器（APScheduler）==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from backend import scheduler
for job in scheduler.job_status():
    print(f"  {job.get('name') or job.get('id'):<20} {job.get('next_run') or job.get('trigger') or '-'}")
PY

echo
echo "=== 3. 系统 cron ==="
crontab -l 2>/dev/null | grep -v '^#' | grep -E 'notify_push|life-assistant' || echo "  （没有 cron 任务）"

echo
echo "=== 4. 结论 ==="
T=$(DORM_DATA_DIR=/www/dorm-data .venv/bin/python -c "
import sys; sys.path.insert(0,'.')
from backend.database import SessionLocal
from backend.services import settings_service as ss
db=SessionLocal(); print(ss.get_setting(db,'qq_report_time')); db.close()
")
if [ "$T" = "22:40" ]; then
  echo "  ✅ 群汇报时间 = 22:40（正确）"
else
  echo "  ❌ 群汇报时间 = $T（应为 22:40）"
fi
