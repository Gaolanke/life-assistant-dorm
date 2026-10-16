#!/usr/bin/env bash
# 最终验证：测试 + 状态
set -u
cd /www/dorm || exit 1
export DORM_DATA_DIR=/www/dorm-data

echo "=== 测试 ==="
for t in test_qqbot test_qqbot_ws test_notify; do
  printf '  %-18s ' "$t"
  .venv/bin/python "scripts/$t.py" 2>&1 | grep -oE '通过 [0-9]+ 项，失败 [0-9]+ 项' | tail -1 || echo "未取到结果"
done

echo
echo "=== 最终配置 ==="
.venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from sqlalchemy import select
from backend.database import SessionLocal
from backend.models import BotGroup
from backend.services import settings_service as ss

db = SessionLocal()
print(f"  机器人 AppID   = {ss.get_setting(db, 'qqbot_app_id')}")
print(f"  推送目标群     = {ss.get_setting(db, 'qqbot_groups')}")
print(f"  推送开关       = {ss.get_setting(db, 'qqbot_enabled')}")
rows = db.execute(select(BotGroup)).scalars().all()
print(f"  已上报群记录   = {len(rows)} 条")
for r in rows:
    print(f"      {r.group_openid}  最近消息={str(r.last_message)[:24]!r}  {r.last_seen}")
db.close()
PY

echo
echo "=== 服务状态 ==="
echo -n "  dorm: "; systemctl is-active dorm
echo -n "  cloudflared: "; systemctl is-active cloudflared
