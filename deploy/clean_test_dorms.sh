#!/usr/bin/env bash
# 清理测试套件在生产库里创建的测试宿舍（3-xxx 系列）
set -eu
cd /www/dorm || exit 1

DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from sqlalchemy import select
from backend.database import SessionLocal
from backend.models import Dorm, Member, Report, ReportCheckin

db = SessionLocal()
print("=== 清理前 ===")
for d in db.execute(select(Dorm).order_by(Dorm.room_no)).scalars():
    n = len([m for m in d.members])
    print(f"  {d.room_no:<8} 人员 {n}")

# 测试用的宿舍号都是 3-2xx / 3-3xx 这种；真实宿舍是 4-1xx / 6-2xx
TEST_PREFIX = ("3-",)
removed = []
for d in db.execute(select(Dorm)).scalars():
    if d.room_no.startswith(TEST_PREFIX):
        removed.append(d.room_no)
        for r in db.execute(select(Report).where(Report.dorm_id == d.id)).scalars():
            for c in list(r.checks):
                db.delete(c)
            db.delete(r)
        for m in list(d.members):
            db.delete(m)
        db.delete(d)

# 清掉测试写进去的填报（宿舍已不存在）
for r in db.execute(select(Report)).scalars().all():
    if r.dorm_id not in {d.id for d in db.execute(select(Dorm)).scalars()}:
        for c in list(r.checks):
            db.delete(c)
        db.delete(r)

db.commit()
print()
print("删除的测试宿舍:", ", ".join(removed) if removed else "无")
print()
print("=== 清理后 ===")
for d in db.execute(select(Dorm).order_by(Dorm.room_no)).scalars():
    print(f"  {d.room_no:<8} 人员 {len(list(d.members))}")
print()
print(f"  宿舍 {db.query(Dorm).count()} / 人员 {db.query(Member).count()} / 填报 {db.query(Report).count()}")
db.close()
PY
