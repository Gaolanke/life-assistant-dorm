#!/usr/bin/env bash
# 验证新机器人的凭证与长连接
set -u
cd /www/dorm || exit 1
export DORM_DATA_DIR=/www/dorm-data

echo "=== 服务状态 ==="
echo -n "  dorm: "; systemctl is-active dorm

echo
echo "=== 当前凭证 ==="
.venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from backend.services import settings_service as ss
from backend.database import SessionLocal
db = SessionLocal()
print(f"  AppID     = {ss.get_setting(db, 'qqbot_app_id')}")
sec = ss.get_setting(db, "qqbot_secret")
print(f"  AppSecret = 长度 {len(sec)}，前4位 {sec[:4]}***")
db.close()
PY

echo
echo "=== 用新凭证取 token ==="
.venv/bin/python - <<'PY'
import asyncio
import sys
sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.services import push_service
db = SessionLocal()
tok, reason = asyncio.run(push_service.get_access_token(db, force=True, retries=2, timeout=15))
print(f"  {'✅ 取到 token，长度 ' + str(len(tok)) if tok else '❌ ' + reason}")
db.close()
PY

echo
echo "=== 网关日志（最近 10 条）==="
grep -iE 'qqbot.gateway' /www/dorm-data/logs/service.log | tail -10
