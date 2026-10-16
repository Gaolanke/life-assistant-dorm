#!/usr/bin/env bash
# 部署带重试的 token 获取逻辑，并做最终端到端验证
set -u
cd /www/dorm || exit 1

echo "=== 1. 更新代码 ==="
tar -xzf /root/life_retry.tar.gz -C /www/dorm
.venv/bin/python -c "import nacl" 2>/dev/null || .venv/bin/pip install -q PyNaCl==1.6.2
systemctl restart dorm
sleep 6
systemctl is-active dorm

echo
echo "=== 2. 真实调用：换 token（带重试） ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import asyncio
import sys
sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.services import push_service

db = SessionLocal()
token, reason = asyncio.run(push_service.get_access_token(db, force=True))
if token:
    print("  ✅ 拿到 access_token（长度 %d）" % len(token))
else:
    print("  ❌ 失败:", reason)
db.close()
PY

echo
echo "=== 3. 公网回调校验（QQ 后台保存地址会走这个） ==="
curl -s -X POST -H 'Content-Type: application/json' \
  -d '{"op":13,"d":{"plain_token":"FinalCheck123","event_ts":"1730000999"}}' \
  http://111.228.38.170:8090/api/qqbot/events
echo

echo
echo "=== 4. 通道自检 ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python scripts/notify_push.py check 2>&1 | tail -4 || true

echo
echo "=== 5. 当前配置 ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.services import settings_service as ss
from backend.services.push_service import mask_secret
db = SessionLocal()
for key in ('qqbot_app_id', 'qqbot_secret', 'qqbot_enabled', 'qqbot_groups', 'qqbot_fallback_email'):
    value = ss.get_setting(db, key)
    if key == 'qqbot_secret' and value:
        value = mask_secret(value)
    print(f"  {key:<24} = {value!r}")
db.close()
PY
rm -f /root/life_retry.tar.gz
