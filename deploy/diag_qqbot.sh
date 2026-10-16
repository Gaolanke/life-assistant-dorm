#!/usr/bin/env bash
# 诊断 QQ 通道：网络可达性 + 回调 500 的真实原因
set -u
cd /www/dorm || exit 1

echo "=== 1. 服务日志里最近的异常 ==="
journalctl -u dorm -n 120 --no-pager 2>/dev/null | grep -A15 -iE "traceback|error|exception" | tail -30 || echo "  日志里没有异常"

echo
echo "=== 2. 本机打回调（看详细响应） ==="
curl -s -i -X POST -H 'Content-Type: application/json' \
  -d '{"op":13,"d":{"plain_token":"T123","event_ts":"1730000123"}}' \
  http://127.0.0.1:8090/api/qqbot/events | head -20

echo
echo "=== 3. 公网打回调 ==="
curl -s -i -X POST -H 'Content-Type: application/json' \
  -d '{"op":13,"d":{"plain_token":"T123","event_ts":"1730000123"}}' \
  http://111.228.38.170:8090/api/qqbot/events | head -12

echo
echo "=== 4. 和腾讯的连通性 ==="
for host in bots.qq.com q.qq.com api.sgroup.qq.com sandbox.api.sgroup.qq.com; do
  if getent hosts "$host" >/dev/null 2>&1; then
    ip=$(getent hosts "$host" | head -1 | awk '{print $1}')
    code=$(curl -s -o /dev/null -m 8 -w '%{http_code}' "https://$host/" 2>/dev/null || echo "超时")
    printf '  %-32s DNS=%s  HTTPS=%s\n' "$host" "$ip" "$code"
  else
    printf '  %-32s DNS解析失败\n' "$host"
  fi
done

echo
echo "=== 5. 直接换 token（带详细错误） ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
import httpx
from backend.database import SessionLocal
from backend.services import settings_service as ss

db = SessionLocal()
appid = ss.get_setting(db, 'qqbot_app_id')
secret = ss.get_setting(db, 'qqbot_secret')
db.close()
print("  AppID 长度:", len(appid), " Secret 长度:", len(secret))

for url in ('https://bots.qq.com/app/getAppAccessToken',
            'https://sandbox.api.sgroup.qq.com/app/getAppAccessToken'):
    try:
        r = httpx.post(url, json={'appId': appid, 'clientSecret': secret}, timeout=12)
        print(" ", url, "->", r.status_code, r.text[:160])
    except Exception as exc:
        print(" ", url, "->", type(exc).__name__, str(exc)[:120])
PY
