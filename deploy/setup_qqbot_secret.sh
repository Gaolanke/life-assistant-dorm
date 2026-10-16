#!/usr/bin/env bash
# 写入 QQ 官方机器人 AppSecret 并验证凭证是否有效
set -u
cd /www/dorm || exit 1
SECRET="${1:?用法: setup_qqbot_secret.sh <AppSecret>}"

echo "=== 1. 写入 AppSecret（不打印明文） ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - "$SECRET" <<'PY'
import sys
sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.services import settings_service as ss
from backend.services.push_service import mask_secret
db = SessionLocal()
ss.ensure_settings(db)
ss.set_setting(db, 'qqbot_secret', sys.argv[1])
db.commit()
print("  AppID    =", ss.get_setting(db, 'qqbot_app_id'))
print("  AppSecret=", mask_secret(ss.get_setting(db, 'qqbot_secret')))
PY

echo
echo "=== 2. 真去 QQ 官方接口换 access_token（验证凭证） ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import asyncio
import sys
sys.path.insert(0, '.')
import httpx
from backend.database import SessionLocal
from backend.services import settings_service as ss
from backend.services import push_service

db = SessionLocal()

# 先看服务器能不能连上 bots.qq.com
try:
    r = httpx.post(
        push_service.TOKEN_URL,
        json={
            'appId': ss.get_setting(db, 'qqbot_app_id'),
            'clientSecret': ss.get_setting(db, 'qqbot_secret'),
        },
        timeout=20,
    )
    data = r.json()
except Exception as exc:
    print("  连不上/解析失败:", exc)
    data = {}

if data.get('access_token'):
    print("  ✅ 凭证有效！拿到了 access_token（长度 %d，有效期 %s 秒）"
          % (len(data['access_token']), data.get('expires_in')))
elif data:
    print("  ❌ 官方返回错误：", str(data)[:300])
    print("  → 常见原因：AppID/AppSecret 不匹配，或该机器人还没发布/未开通群聊场景")
else:
    print("  ⚠ 没拿到结果，请看上面的错误")

# 顺便看看沙箱地址通不通
try:
    r2 = httpx.get('https://sandbox.api.sgroup.qq.com', timeout=8)
    print("  沙箱域名可达：HTTP", r2.status_code)
except Exception as exc:
    print("  沙箱域名：", type(exc).__name__)

db.close()
PY

echo
echo "=== 3. 回调地址公网可达性 + 签名校验 ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
import httpx
from backend.database import SessionLocal
from backend.services import settings_service as ss
from backend.routers.qqbot import _ed25519_verify

db = SessionLocal()
secret = ss.get_setting(db, 'qqbot_secret')
db.close()

ts, token = '1730000123', 'ServerCheckToken123'
try:
    r = httpx.post('http://111.228.38.170:8090/api/qqbot/events',
                   json={'op': 13, 'd': {'plain_token': token, 'event_ts': ts}}, timeout=15)
    data = r.json()
    ok = _ed25519_verify(secret, ts + token, data.get('signature', ''))
    print("  HTTP", r.status_code, "签名校验:", "✅ 通过" if ok else "❌ 不通过")
    if ok:
        print("  → QQ 开放平台后台保存这个回调地址会成功：")
        print("     http://111.228.38.170:8090/api/qqbot/events")
except Exception as exc:
    print("  请求失败:", exc)
PY

echo
echo "=== 4. 通道自检 ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python scripts/notify_push.py check 2>&1 | tail -5 || true

echo
echo "=== 5. 群列表 ==="
curl -s http://127.0.0.1:8091/api/qqbot/groups | head -c 200
echo
