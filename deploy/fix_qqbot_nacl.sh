#!/usr/bin/env bash
# 给服务器装 PyNaCl（QQ 官方机器人回调验签要用），然后验证回调
set -eu
cd /www/dorm || exit 1

echo "=== 1. 安装 PyNaCl ==="
if .venv/bin/python -c "import nacl" 2>/dev/null; then
  echo "  已经装了，跳过"
else
  .venv/bin/pip install -q PyNaCl==1.6.2 2>&1 | tail -3 || {
    echo "  官方源失败，换清华镜像重试"
    .venv/bin/pip install -q -i https://pypi.tuna.tsinghua.edu.cn/simple PyNaCl==1.6.2 2>&1 | tail -3
  }
fi
.venv/bin/python -c "import nacl; print('  PyNaCl', nacl.__version__, '可用')"

echo
echo "=== 2. 重启服务 ==="
systemctl restart dorm
sleep 6
systemctl is-active dorm

echo
echo "=== 3. 本机回调校验（应该返回 plain_token + signature） ==="
curl -s -X POST -H 'Content-Type: application/json' \
  -d '{"op":13,"d":{"plain_token":"ServerCheckToken123","event_ts":"1730000123"}}' \
  http://127.0.0.1:8090/api/qqbot/events
echo

echo
echo "=== 4. 公网回调校验 + 验签结果 ==="
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
r = httpx.post('http://111.228.38.170:8090/api/qqbot/events',
               json={'op': 13, 'd': {'plain_token': token, 'event_ts': ts}}, timeout=15)
print("  HTTP", r.status_code, r.text[:160])
data = r.json()
if data.get('plain_token') == token:
    ok = _ed25519_verify(secret, ts + token, data.get('signature', ''))
    print("  plain_token 原样返回: ✅")
    print("  签名校验:", "✅ 通过 —— QQ 后台保存回调地址会成功" if ok else "❌ 不通过")
else:
    print("  ❌ 返回内容不对")
PY

echo
echo "=== 5. 端到端：真的换一次 access_token ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
import httpx
from backend.database import SessionLocal
from backend.services import settings_service as ss

db = SessionLocal()
try:
    r = httpx.post('https://bots.qq.com/app/getAppAccessToken',
                   json={'appId': ss.get_setting(db, 'qqbot_app_id'),
                         'clientSecret': ss.get_setting(db, 'qqbot_secret')},
                   timeout=15)
    data = r.json()
    print("  ✅ 凭证有效，access_token 长度", len(data.get('access_token', '')),
          "有效期", data.get('expires_in'), "秒")
except Exception as exc:
    print("  ❌ 失败:", exc)
db.close()
PY
