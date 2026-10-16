#!/usr/bin/env bash
# 清理不用的推送群：逐个测试能否发送，保留能发的
set -u
cd /www/dorm || exit 1
export DORM_DATA_DIR=/www/dorm-data

.venv/bin/python - <<'PY'
import asyncio
import sys

sys.path.insert(0, '.')
from sqlalchemy import select
from backend.database import SessionLocal
from backend.models import BotGroup
from backend.services import push_service, settings_service as ss

db = SessionLocal()
raw = ss.get_setting(db, "qqbot_groups")
targets = [g.strip() for g in raw.replace("，", ",").split(",") if g.strip()]
print(f"当前推送目标 {len(targets)} 个：")

groups_rows = {g.group_openid: g for g in db.execute(select(BotGroup)).scalars()}
for t in targets:
    has = "有上报记录" if t in groups_rows else "无上报记录"
    print(f"  {t}   （{has}）")

print()
print("逐个测试能否发送（每群试 2 次）：")
ok_list, bad_list = [], []
for t in targets:
    r = asyncio.run(push_service.send_group_message(
        db, t, "【生活助手】群可用性检测，收到请忽略。", attempts=2))
    status = "✅ 可发" if r.get("ok") else f"❌ {str(r.get('message'))[:40]}"
    print(f"  {t[:24]}…  {status}")
    (ok_list if r.get("ok") else bad_list).append(t)

print()
print(f"可用 {len(ok_list)} 个，不可用 {len(bad_list)} 个")
print(f"  可用: {ok_list}")
print(f"  不可用: {bad_list}")
db.close()
PY
