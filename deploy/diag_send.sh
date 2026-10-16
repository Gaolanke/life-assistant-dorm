#!/usr/bin/env bash
# 直接调 QQ 官方发消息接口，看真实响应
set -u
cd /www/dorm || exit 1

TOK=$(DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import asyncio, sys
sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.services import push_service
db = SessionLocal()
token, reason = asyncio.run(push_service.get_access_token(db, force=True))
print(token or '')
db.close()
PY
)
GROUP=$(DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.services import settings_service as ss
db = SessionLocal()
print(ss.get_setting(db, 'qqbot_groups'))
db.close()
PY
)
echo "token 长度: ${#TOK}  群: $GROUP"

echo
echo "=== 1. 发消息接口（超时 30 秒） ==="
curl -s -m 30 -w '\nHTTP %{http_code}  耗时 %{time_total}s\n' \
  -X POST "https://api.sgroup.qq.com/v2/groups/$GROUP/messages" \
  -H "Authorization: QQBot $TOK" -H 'Content-Type: application/json' \
  -d '{"content":"【测试】生活助手班费公示，收到请忽略。","msg_type":0}'

echo
echo "=== 2. 机器人自身信息（GET，验证 token 权限） ==="
curl -s -m 30 -w '\nHTTP %{http_code}  耗时 %{time_total}s\n' \
  "https://api.sgroup.qq.com/v2/users/@me" \
  -H "Authorization: QQBot $TOK"

echo
echo "=== 3. 群信息（看机器人是否真在群里） ==="
curl -s -m 30 -w '\nHTTP %{http_code}  耗时 %{time_total}s\n' \
  "https://api.sgroup.qq.com/v2/groups/$GROUP" \
  -H "Authorization: QQBot $TOK"

echo
echo "=== 4. 网关信息（对照，这个之前是通的） ==="
curl -s -m 20 -w '\nHTTP %{http_code}  耗时 %{time_total}s\n' \
  "https://api.sgroup.qq.com/gateway" \
  -H "Authorization: QQBot $TOK" | head -c 200
