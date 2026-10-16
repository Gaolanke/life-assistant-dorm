#!/usr/bin/env bash
# 验证「每个推送入口都走 QQ 官方机器人，并且带重试后能发出去」
set -u
cd /www/dorm || exit 1

echo "=== 1. 长连接 ==="
curl -s http://127.0.0.1:8091/api/qqbot/status | head -c 180
echo

echo
echo "=== 2. 逐个入口发一次（重试最多 4 次，所以慢一点是正常的） ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import asyncio
import sys

sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.services import notify_service, push_service

db = SessionLocal()

async def main():
    print("  ① 定时群汇报（scheduler 用的就是它）")
    r1 = await notify_service.send_group_report(db, trigger="manual")
    print(f"     通道={r1.get('channel')} ok={r1.get('ok')} {str(r1.get('message'))[:60]}")

    print("  ② 未填提醒")
    r2 = await notify_service.send_missing_reminder(db, trigger="manual")
    print(f"     通道={r2.get('channel')} ok={r2.get('ok')} {str(r2.get('message'))[:60]}")

    print("  ③ 自定义消息")
    r3 = await push_service.deliver_notification(
        db, title="测试", content="【生活助手】全部通道已切到 QQ 官方机器人 ✅", scene="test"
    )
    print(f"     通道={r3.get('channel')} ok={r3.get('ok')} {str(r3.get('message'))[:60]}")
    for item in r3.get("results", []):
        print(f"       - {item.get('channel')} attempt={item.get('attempt')} {str(item.get('message'))[:50]}")

asyncio.run(main())
db.close()
PY

echo
echo "=== 3. 网页接口入口 ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
import httpx
base = 'http://127.0.0.1:8091'
c = httpx.Client(base_url=base, timeout=180)
tok = c.post('/api/auth/login', json={'username': 'admin', 'password': '344940'}).json().get('token', '')
h = {'X-Session-Token': tok}
for path, body in (
    ('/api/onebot/send', None),
    ('/api/onebot/remind', None),
    ('/api/fund/push', {'scope': 'latest'}),
    ('/api/settings/test', {'kind': 'notify'}),
):
    try:
        res = c.post(path, headers=h, json=body) if body is not None else c.post(path, headers=h)
        d = res.json()
        print(f"  {path:<24} HTTP {res.status_code} 通道={d.get('channel')} ok={d.get('ok')}")
    except Exception as exc:
        print(f"  {path:<24} 异常 {type(exc).__name__}")
print("  状态:", c.get('/api/onebot/status', headers=h).json().get('message'))
PY

echo
echo "=== 4. 推送日志 ==="
curl -s http://127.0.0.1:8091/api/logs/push?limit=8 | head -c 500
echo
