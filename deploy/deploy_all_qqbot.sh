#!/usr/bin/env bash
# 部署「全部切到 QQ 官方机器人」，并逐个验证每个推送入口
set -u
cd /www/dorm || exit 1

echo "=== 1. 解包并重启 ==="
tar -xzf /root/life_all_qqbot.tar.gz -C /www/dorm
systemctl restart dorm
sleep 8
systemctl is-active dorm

echo
echo "=== 2. 长连接状态 ==="
curl -s http://127.0.0.1:8091/api/qqbot/status | head -c 200
echo

echo
echo "=== 3. 通道判定 ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.services import notify_service, settings_service as ss
db = SessionLocal()
print("  新通道可用:", notify_service._new_channel_ready(db))
print("  qqbot_enabled:", ss.get_setting(db, 'qqbot_enabled'), "| 群:", ss.get_setting(db, 'qqbot_groups'))
db.close()
PY

echo
echo "=== 4. 逐个入口真发一次（每个入口都该走 QQ 官方机器人） ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import asyncio
import sys

sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.services import notify_service

db = SessionLocal()

async def main():
    print("  ① 手动群汇报（notify_service.send_group_report）")
    r1 = await notify_service.send_group_report(db, trigger="manual")
    print("     通道:", r1.get("channel"), "| 结果:", "✅" if r1.get("ok") else "❌", r1.get("message"))

    print("  ② 手动未填提醒（notify_service.send_missing_reminder）")
    r2 = await notify_service.send_missing_reminder(db, trigger="manual")
    print("     通道:", r2.get("channel"), "| 结果:", "✅" if r2.get("ok") else "❌", r2.get("message"))

asyncio.run(main())
db.close()
PY

echo
echo "=== 5. 网页接口入口 ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
import httpx
base = 'http://127.0.0.1:8091'
c = httpx.Client(base_url=base, timeout=60)
tok = c.post('/api/auth/login', json={'username': 'admin', 'password': '344940'}).json().get('token', '')
h = {'X-Session-Token': tok}
for path, body in (
    ('/api/onebot/send', None),
    ('/api/onebot/remind', None),
    ('/api/fund/push', {'scope': 'latest'}),
):
    try:
        res = c.post(path, headers=h, json=body) if body is not None else c.post(path, headers=h)
        data = res.json()
        print(f"  {path:<22} HTTP {res.status_code} 通道={data.get('channel')} ok={data.get('ok')} {str(data.get('message'))[:50]}")
    except Exception as exc:
        print(f"  {path:<22} 异常 {exc}")
print("  状态接口:", c.get('/api/onebot/status', headers=h).json().get('message'))
PY

echo
echo "=== 6. 推送日志（应该都是 QQ 群 / 成功） ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.services import notify_service
db = SessionLocal()
for row in notify_service.recent_logs(db, 8):
    print(f"  {row['created_at']} [{row['channel_text']}] {row['scene_text']} -> {row['status_text']} {str(row['detail'])[:40]}")
db.close()
PY
rm -f /root/life_all_qqbot.tar.gz
