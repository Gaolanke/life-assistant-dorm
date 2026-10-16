#!/usr/bin/env bash
# 确认网关已连上，并列出已记录的群
set -u
cd /www/dorm || exit 1
export DORM_DATA_DIR=/www/dorm-data

echo "=== 网关连接情况 ==="
grep -iE '长连接已建立|连接中：|出错|鉴权' /www/dorm-data/logs/service.log | tail -8

echo
echo "=== 已记录的群 ==="
.venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.models import BotGroup
db = SessionLocal()
rows = db.query(BotGroup).all()
print(f"  共 {len(rows)} 个群：")
for r in rows:
    print(f"    openid = {r.group_openid}")
    print(f"      最近消息 = {str(r.last_message)[:40]!r}  次数 = {r.message_count}  时间 = {r.last_seen}")
db.close()
PY

echo
echo "=== 服务状态 ==="
echo -n "  dorm: "; systemctl is-active dorm
