#!/usr/bin/env bash
# 确认后台 WebSocket 常驻任务在服务进程里运行
set -u
cd /www/dorm || exit 1

echo "=== 1. 相关配置 ==="
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.services import settings_service as ss
db = SessionLocal()
ss.ensure_settings(db)
for key in ('qqbot_enabled', 'qqbot_ws_enabled', 'qqbot_app_id', 'qqbot_groups'):
    print(f"  {key:<20} = {ss.get_setting(db, key)!r}")
db.close()
PY

echo
echo "=== 2. 服务启动日志（看长连接任务有没有起来） ==="
journalctl -u dorm --since "-10min" --no-pager 2>/dev/null | grep -iE "长连接|WebSocket|qqbot|定时任务|已启动" | tail -12 || echo "  没找到"

echo
echo "=== 3. 进程内的线程/任务 ==="
PID=$(systemctl show dorm -p MainPID --value)
echo "  主进程 PID: $PID"
ls /proc/$PID/task 2>/dev/null | wc -l | sed 's/^/  线程数: /'

echo
echo "=== 4. 完整日志尾部 ==="
journalctl -u dorm -n 25 --no-pager 2>/dev/null | tail -25
