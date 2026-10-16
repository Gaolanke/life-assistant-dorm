#!/usr/bin/env bash
# 验证「填报提醒」定时任务已就位（只验证，不向群里发消息）
set -u
cd /www/dorm || exit 1
export DORM_DATA_DIR=/www/dorm-data

echo "=== 1. 设置公开端网址 ==="
.venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.services import settings_service as ss
from backend.defaults import DEFAULTS

db = SessionLocal()
# 把新增的默认值写进库
added = ss.ensure_defaults(db) if hasattr(ss, "ensure_defaults") else None
db.commit()

ss.set_setting(db, "site_public_url", "https://xiaoaiyun.top")
db.commit()

print("  相关设置：")
for k in (
    "site_public_url",
    "fill_remind_enabled",
    "fill_remind_time",
    "fill_remind_mention_all",
    "report_deadline",
    "qq_report_time",
):
    print(f"    {k:<24} = {ss.get_setting(db, k)!r}")
db.close()
PY

echo
echo "=== 2. 定时任务 ==="
.venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from backend import scheduler
jobs = scheduler.build_scheduler().get_jobs()
for j in jobs:
    print(f"  {j.id:<18} {j.trigger}")
ids = [j.id for j in jobs]
print()
print(f"  填报提醒(fill_remind) 已注册: {'✅' if 'fill_remind' in ids else '❌'}")
print(f"  未填报提醒(missing_reminder) 已删除: {'✅' if 'missing_reminder' not in ids else '❌ 还在'}")
PY

echo
echo "=== 3. 定时提醒的文案（预览，不发送）==="
.venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.services import notify_service

db = SessionLocal()
print("  ───────── 群里将会收到的内容 ─────────")
for line in notify_service.build_fill_reminder(db).splitlines():
    print(f"  | {line}")
print("  ─────────────────────────────────────")
print()
print(f"  会 @全体成员: {notify_service.ss.get_bool(db, 'fill_remind_mention_all', True)}")
db.close()
PY
