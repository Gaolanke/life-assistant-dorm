#!/usr/bin/env bash
# 确认新群采集、发送结果与通道状态
set -u
cd /www/dorm || exit 1
export DORM_DATA_DIR=/www/dorm-data

echo "=== 1. 已采集的群 ==="
.venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.models import BotGroup
db = SessionLocal()
rows = db.query(BotGroup).order_by(BotGroup.id).all()
print(f"  共 {len(rows)} 个群：")
for r in rows:
    print(f"    [{r.id}] {r.group_openid}")
    print(f"         最近消息 = {str(r.last_message)[:44]!r}")
    print(f"         次数 = {r.message_count}   时间 = {r.last_seen}")
db.close()
PY

echo
echo "=== 2. 当前推送目标 ==="
.venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.services import settings_service as ss
db = SessionLocal()
print(f"  qqbot_groups = {ss.get_setting(db, 'qqbot_groups')!r}")
print(f"  qqbot_enabled = {ss.get_setting(db, 'qqbot_enabled')!r}")
db.close()
PY

echo
echo "=== 3. 最近的推送日志 ==="
.venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.services import notify_service
db = SessionLocal()
for r in notify_service.recent_logs(db, 8):
    print(f"  {r.get('created_at')} [{r.get('channel_text')}] {r.get('scene_text')} -> {r.get('status_text')}")
    print(f"     目标={str(r.get('target'))[:60]}")
    print(f"     详情={str(r.get('detail'))[:70]}")
db.close()
PY

echo
echo "=== 4. 回调 / 长连接状态 ==="
grep -iE '回调校验|长连接已建立|网关地址获取失败' /www/dorm-data/logs/service.log | tail -8

echo
echo "=== 5. 长连接 ==="
curl -s -X POST http://127.0.0.1:8091/api/auth/login -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"344940"}' 2>/dev/null | head -c 60
echo
