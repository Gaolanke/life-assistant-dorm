#!/usr/bin/env bash
# 部署班费推送改造，并端到端验证「班费发到 QQ 群」
set -u
cd /www/dorm || exit 1

echo "=== 1. 解包并重启 ==="
tar -xzf /root/life_fundpush.tar.gz -C /www/dorm
systemctl restart dorm
sleep 7
systemctl is-active dorm

echo
echo "=== 2. 班费概览里的推送通道 ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.routers.fund import fund_push_target, push_channel_text
from backend.services import settings_service as ss
db = SessionLocal()
print("  推送目标(群 openid):", fund_push_target(db))
print("  当前通道:", push_channel_text(db))
print("  qqbot_enabled:", ss.get_setting(db, 'qqbot_enabled'))
print("  qqbot_groups :", ss.get_setting(db, 'qqbot_groups'))
db.close()
PY

echo
echo "=== 3. 真发一条班费公示到 QQ 群 ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import asyncio
import sys
sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.routers.fund import fund_push_target
from backend.services import fund_service, push_service

db = SessionLocal()
msg = fund_service.render_preview(db, 'latest', None)
print("  要发的内容:")
print("   " + msg['text'].replace('\n', '\n   '))
result = asyncio.run(push_service.deliver_notification(
    db, title='班费公示', content=msg['text'], scene='fund_report',
    group_openid=fund_push_target(db),
))
print()
print("  通道:", result.get('channel'), "| 结果:", "✅" if result.get('ok') else "❌", result.get('message'))
for item in result.get('results', []):
    print("   ", "✅" if item.get('ok') else "❌", item.get('channel'), item.get('group') or '', item.get('message'))
db.close()
PY

echo
echo "=== 4. 推送日志 ==="
curl -s http://127.0.0.1:8091/api/logs/push 2>/dev/null | head -c 300
echo
rm -f /root/life_fundpush.tar.gz
