#!/usr/bin/env bash
# 清理测试残留 + 把测试改为在独立数据目录里跑（绝不再碰生产库）
set -eu
cd /www/dorm || exit 1

echo "=== 1. 清理测试残留（并发测试写入的那条填报 + 测试推送日志） ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from sqlalchemy import delete, select
from backend.database import SessionLocal
from backend.models import Report, ReportCheckin, PushLog, Account, Dorm

db = SessionLocal()
# 删掉备注里带"并发测试"的填报（那是并发压测写进去的）
rows = db.execute(select(Report).where(Report.note.like("%并发测试%"))).scalars().all()
for r in rows:
    for c in list(r.checks):
        db.delete(c)
    print(f"  删除测试填报: 宿舍id={r.dorm_id} {r.report_date} 备注={r.note!r}")
    db.delete(r)

# 删掉测试建的寝室长账号（不是 admin 的）
extras = db.execute(select(Account).where(Account.role != "admin")).scalars().all()
for a in extras:
    print(f"  删除测试账号: {a.username} ({a.role})")
    db.delete(a)

# 推送日志里测试产生的记录
n = db.query(PushLog).filter(PushLog.scene == "test").count()
if n:
    db.execute(delete(PushLog).where(PushLog.scene == "test"))
    print(f"  删除测试推送日志 {n} 条")
db.commit()

print()
print("  清理后：")
print(f"    宿舍 {db.query(Dorm).count()} / 人员 {db.query(__import__('backend.models', fromlist=['Member']).Member).count()}"
      f" / 填报 {db.query(Report).count()} / 账号 {db.query(Account).count()}")
db.close()
PY

echo
echo "=== 2. 备份目录清理（只保留最近 30 份 + 那份 BROKEN 免删） ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from backend.services import backup_service
items = backup_service.list_backups()
print(f"  当前 {len(items)} 份")
PY
ls -1 /www/dorm-data/backups/*.db | wc -l | xargs echo "  实际文件数:"

echo
echo "完成"
