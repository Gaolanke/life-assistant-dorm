#!/usr/bin/env bash
# 验证回调接口在两个域名上都可用
set -u

echo "=== 服务状态 ==="
echo -n "  dorm: "; systemctl is-active dorm

echo
echo "=== 回调接口（两个域名都应 200）==="
for h in xiaoaiyun.top admin.xiaoaiyun.top; do
  code=$(curl -s -o /dev/null -m 20 -w '%{http_code}' -X POST "https://$h/api/qqbot/events" \
    -H 'Content-Type: application/json' \
    -d '{"op":13,"d":{"plain_token":"t123","event_ts":"1728700000"}}')
  printf '  %-24s %s\n' "$h" "$code"
done

echo
echo "=== 当前机器人配置 ==="
cd /www/dorm
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from sqlalchemy import select
from backend.database import SessionLocal
from backend.models import Setting
db = SessionLocal()
for k in ("qqbot_app_id", "qqbot_enabled", "qqbot_ws_enabled"):
    r = db.execute(select(Setting).where(Setting.key == k)).scalar()
    print(f"  {k:<18} = {r.value if r else None!r}")
db.close()
PY

echo
echo "=== 长连接 ==="
grep -iE 'qqbot.gateway' /www/dorm-data/logs/service.log | tail -4
