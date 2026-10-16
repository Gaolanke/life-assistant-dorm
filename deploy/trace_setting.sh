#!/usr/bin/env bash
# 查是谁、什么时候改了 qq_report_time
set -u
cd /www/dorm || exit 1

DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from sqlalchemy import select
from backend.database import SessionLocal
from backend.models import AuditLog, Setting

db = SessionLocal()

print("=== settings 表里 qq_report_time 的原始记录 ===")
row = db.execute(select(Setting).where(Setting.key == "qq_report_time")).scalar()
if row:
    for col in ("key", "value", "group", "updated_at", "created_at"):
        if hasattr(row, col):
            print(f"  {col:<12} = {getattr(row, col)!r}")
else:
    print("  没有这条记录")

print()
print("=== 最近的「修改系统配置」审计记录 ===")
rows = db.execute(
    select(AuditLog).where(AuditLog.action.like("%配置%")).order_by(AuditLog.id.desc()).limit(10)
).scalars().all()
if not rows:
    print("  没有相关记录")
for r in rows:
    print(f"  {getattr(r, 'created_at', '?')} | {getattr(r, 'actor', '?')} | {getattr(r, 'detail', '')[:90]}")

print()
print("=== 最近 12 条审计（不限类型）===")
for r in db.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(12)).scalars().all():
    print(f"  {getattr(r, 'created_at', '?')} | {getattr(r, 'action', '?')} | {str(getattr(r, 'detail', ''))[:70]}")

db.close()
PY
