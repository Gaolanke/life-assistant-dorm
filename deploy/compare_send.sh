#!/usr/bin/env bash
# 对照测试：curl 直连 vs 程序发送（判断是网络还是代码）
set -u
cd /www/dorm || exit 1

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

echo "=== 连测 5 次 curl 发送（看网络稳定性） ==="
for i in 1 2 3 4 5; do
  out=$(curl -s -m 30 -w '|%{http_code}|%{time_total}' -X POST \
    "https://api.sgroup.qq.com/v2/groups/$GROUP/messages" \
    -H "Authorization: QQBot $TOK" -H 'Content-Type: application/json' \
    -d "{\"content\":\"【生活助手】连通性测试 $i\",\"msg_type\":0}" 2>/dev/null)
  code=$(echo "$out" | awk -F'|' '{print $(NF-1)}')
  secs=$(echo "$out" | awk -F'|' '{print $NF}')
  body=$(echo "$out" | awk -F'|' '{print $1}' | head -c 100)
  printf '  第 %s 次: HTTP %s  耗时 %ss  %s\n' "$i" "$code" "$secs" "$body"
  sleep 1
done
