#!/usr/bin/env bash
# 诊断「换群后发不出去」的问题
set -u
cd /www/dorm || exit 1
export DORM_DATA_DIR=/www/dorm-data

echo "############ 1. 长连接状态 ############"
curl -s http://127.0.0.1:8091/api/qqbot/status 2>/dev/null | head -c 400
echo

echo
echo "############ 2. 已记录的群（关键：新群有没有被抓到） ############"
.venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from sqlalchemy import select
from backend.database import SessionLocal
from backend.models import BotGroup, Setting

db = SessionLocal()
rows = db.execute(select(BotGroup).order_by(BotGroup.id)).scalars().all()
print(f"  bot_groups 表共 {len(rows)} 条：")
for r in rows:
    print(f"    id={r.id} 渠道={r.channel} openid={r.group_openid}")
    print(f"      群号={r.group_no!r} 群名={r.name!r}")
    print(f"      最近消息={str(r.last_message)[:40]!r} 次数={r.message_count} 时间={r.last_seen}")

print()
row = db.execute(select(Setting).where(Setting.key == "qqbot_groups")).scalar()
print(f"  当前推送目标 qqbot_groups = {row.value!r}" if row else "  qqbot_groups 未设置")
for k in ("qqbot_enabled", "qqbot_ws_enabled", "qqbot_app_id", "qqbot_sandbox", "qqbot_api"):
    r = db.execute(select(Setting).where(Setting.key == k)).scalar()
    print(f"  {k:<20} = {r.value!r}" if r else f"  {k:<20} = (缺)")
db.close()
PY

echo
echo "############ 3. 最近的推送日志 ############"
.venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.services import notify_service
db = SessionLocal()
for row in notify_service.recent_logs(db, 10):
    print(f"  {row['created_at']} [{row['channel_text']}] {row['scene_text']} -> {row['status_text']}")
    print(f"      目标={str(row['target'])[:50]}")
    print(f"      详情={str(row['detail'])[:90]}")
db.close()
PY

echo
echo "############ 4. 网关日志（看新群消息有没有进来） ############"
grep -iE 'qqbot|群' /www/dorm-data/logs/service.log 2>/dev/null | tail -20

echo
echo "############ 5. 直接测试发送（用当前配置的群） ############"
.venv/bin/python - <<'PY'
import asyncio
import sys
sys.path.insert(0, '.')
from sqlalchemy import select
from backend.database import SessionLocal
from backend.models import BotGroup
from backend.services import push_service

db = SessionLocal()
groups = db.execute(select(BotGroup).order_by(BotGroup.id.desc())).scalars().all()
if not groups:
    print("  没有记录到任何群")
else:
    target = groups[0].group_openid
    print(f"  用最新记录的群测试：{target}")
    result = asyncio.run(push_service.send_group_message(
        db, target, "【测试】生活助手换群测试，收到请忽略。", attempts=2))
    print(f"  结果: {'✅' if result.get('ok') else '❌'} {result.get('message')}")
    if result.get("code"):
        print(f"  错误码: {result.get('code')}")
    if result.get("data"):
        print(f"  原始返回: {str(result.get('data'))[:200]}")
db.close()
PY
