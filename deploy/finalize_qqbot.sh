#!/usr/bin/env bash
# 打开 QQ 机器人推送开关，并把定时任务改成"没配群时不发降级邮件"
set -u
cd /www/dorm || exit 1

echo "=== 1. 打开推送开关 ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.services import settings_service as ss
db = SessionLocal()
ss.ensure_settings(db)
ss.set_setting(db, 'qqbot_enabled', '1')
db.commit()
for key in ('qqbot_app_id', 'qqbot_enabled', 'qqbot_groups', 'qqbot_fallback_email'):
    print(f"  {key:<24} = {ss.get_setting(db, key)!r}")
db.close()
PY

echo
echo "=== 2. 重装 cron：没配群时不发降级邮件 ==="
APP_DIR=/www/dorm DATA_DIR=/www/dorm-data bash deploy/install_cron.sh >/dev/null 2>&1 || true
TMP=$(mktemp)
crontab -l 2>/dev/null | sed 's|notify_push.py report|notify_push.py --no-email report|; s|notify_push.py remind|notify_push.py --no-email remind|' > "$TMP"
crontab "$TMP"
rm -f "$TMP"
crontab -l | grep life-assistant-notify

echo
echo "=== 3. 通道自检 ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python scripts/notify_push.py check 2>&1 | tail -4

echo
echo "=== 4. 再验证一次公网回调（QQ 后台要用） ==="
curl -s -X POST -H 'Content-Type: application/json' \
  -d '{"op":13,"d":{"plain_token":"ReadyCheck456","event_ts":"1730001111"}}' \
  http://111.228.38.170:8090/api/qqbot/events
echo
