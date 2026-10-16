#!/usr/bin/env bash
# 查审计日志：时间设置是怎么被改成 22:39 的
set -u
cd /www/dorm || exit 1
export DORM_DATA_DIR=/www/dorm-data

.venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from sqlalchemy import select
from backend.database import SessionLocal
from backend.models import AuditLog, Setting

db = SessionLocal()

row = db.execute(select(Setting).where(Setting.key == "qq_report_time")).scalar()
if row:
    print(f"qq_report_time 当前值 = {row.value!r}")
    print(f"  创建时间 = {getattr(row, 'created_at', '?')}")
    print(f"  更新时间 = {getattr(row, 'updated_at', '?')}")

print()
print("=== 最近的「修改系统配置」记录 ===")
for r in db.execute(
    select(AuditLog).where(AuditLog.action.like("%配置%")).order_by(AuditLog.id.desc()).limit(10)
).scalars():
    detail = str(getattr(r, "detail", ""))
    mark = "  ← 含时间字段" if "qq_report_time" in detail or "report_deadline" in detail else ""
    print(f"  {getattr(r, 'created_at', '?')} | {str(detail)[:74]}{mark}")

print()
print("=== 最近 10 条审计（全类型）===")
for r in db.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(10)).scalars():
    print(f"  {getattr(r, 'created_at', '?')} | {getattr(r, 'action', '?')} | {str(getattr(r, 'detail', ''))[:60]}")
db.close()
PY
