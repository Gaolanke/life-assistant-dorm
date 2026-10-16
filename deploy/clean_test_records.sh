#!/usr/bin/env bash
# 清理测试残留（GROUP_OPENID_TEST_* 这类假记录）
set -u
cd /www/dorm || exit 1
export DORM_DATA_DIR=/www/dorm-data

.venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from sqlalchemy import select
from backend.database import SessionLocal
from backend.models import BotGroup
from backend.services import settings_service as ss

db = SessionLocal()
print("=== 清理前 ===")
for r in db.execute(select(BotGroup)).scalars():
    print(f"  id={r.id}  {r.group_openid}  最近={str(r.last_message)[:24]!r}")
print(f"  推送目标 = {ss.get_setting(db, 'qqbot_groups')!r}")

# 测试套件造的假记录：openid 以 GROUP_OPENID_TEST / TEST_ 开头
removed = 0
for r in db.execute(select(BotGroup)).scalars().all():
    if r.group_openid.startswith(("GROUP_OPENID_TEST", "TEST_")):
        print(f"  删除测试记录: {r.group_openid}")
        db.delete(r)
        removed += 1
db.commit()

print()
print("=== 清理后 ===")
rows = db.execute(select(BotGroup)).scalars().all()
for r in rows:
    print(f"  id={r.id}  {r.group_openid}  最近={str(r.last_message)[:24]!r}")
print(f"  剩余群记录 {len(rows)} 条，删除测试记录 {removed} 条")
print(f"  推送目标 = {ss.get_setting(db, 'qqbot_groups')!r}")
db.close()
PY
