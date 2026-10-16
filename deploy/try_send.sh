#!/usr/bin/env bash
# 长连接建立后再试一次发群消息
set -u
cd /www/dorm || exit 1

DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import asyncio
import sys

sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.routers.fund import fund_push_target
from backend.services import fund_service, push_service

db = SessionLocal()
msg = fund_service.render_preview(db, 'latest', None)
print("要发的内容：")
print("  " + msg["text"].replace("\n", "\n  "))
target = fund_push_target(db)
result = asyncio.run(
    push_service.deliver_notification(
        db, title="班费公示", content=msg["text"], scene="fund_report", group_openid=target
    )
)
print()
print("通道:", result.get("channel"), "| 结果:", "✅ 成功" if result.get("ok") else "❌ 失败")
print("说明:", result.get("message"))
for item in result.get("results", []):
    print("  ", "✅" if item.get("ok") else "❌", item.get("channel"), item.get("message"))
db.close()
PY

echo
echo "=== 直接 curl 官方发消息接口（看原始返回） ==="
TOK=$(DORM_DATA_DIR=/www/dorm-data .venv/bin/python -c "
import asyncio,sys; sys.path.insert(0,'.')
from backend.database import SessionLocal
from backend.services import push_service
db=SessionLocal(); t,_=asyncio.run(push_service.get_access_token(db, force=True)); print(t or '')
")
GROUP=$(DORM_DATA_DIR=/www/dorm-data .venv/bin/python -c "
import sys; sys.path.insert(0,'.')
from backend.database import SessionLocal
from backend.services import settings_service as ss
db=SessionLocal(); print(ss.get_setting(db,'qqbot_groups'))
")
curl -s -m 25 -w '\nHTTP %{http_code}\n' -X POST \
  "https://api.sgroup.qq.com/v2/groups/$GROUP/messages" \
  -H "Authorization: QQBot $TOK" -H 'Content-Type: application/json' \
  -d '{"content":"【生活助手】班费公示测试，收到请忽略。","msg_type":0}'
