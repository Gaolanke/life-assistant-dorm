#!/usr/bin/env bash
# 写入 QQ 官方机器人 AppID，并检查有没有群消息上报
set -u
cd /www/dorm || exit 1
APPID="${1:-1905764281}"

echo "=== 1. 写入 AppID ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - "$APPID" <<'PY'
import sys
sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.services import settings_service as ss
db = SessionLocal()
ss.ensure_settings(db)
ss.set_setting(db, 'qqbot_app_id', sys.argv[1])
db.commit()
print("  qqbot_app_id =", ss.get_setting(db, 'qqbot_app_id'))
print("  qqbot_enabled =", ss.get_setting(db, 'qqbot_enabled'))
print("  qqbot_groups =", repr(ss.get_setting(db, 'qqbot_groups')))
PY

echo
echo "=== 2. 有没有收到过群消息上报（能从中拿到群 openid） ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.models import AuditLog
db = SessionLocal()
rows = db.query(AuditLog).filter(AuditLog.action.like('%QQ%') | AuditLog.action.like('%群%')).order_by(AuditLog.id.desc()).limit(10).all()
if not rows:
    print("  暂时没有任何群消息上报记录")
    print("  → 需要先把机器人拉进群，并在群里 @机器人 发一句话")
else:
    for row in rows:
        print(f"  {row.created_at} [{row.action}] {row.target} {row.detail[:60]}")
db.close()
PY

echo
echo "=== 3. 服务状态 ==="
systemctl is-active dorm
echo
echo "=== 4. 最近服务日志里和 QQ 相关的行 ==="
journalctl -u dorm -n 200 --no-pager 2>/dev/null | grep -iE "qqbot|onebot|群消息|hook" | tail -8 || echo "  （日志里没有相关内容）"
