#!/usr/bin/env bash
# 连续验证 token 获取的稳定性（跑 6 次）
set -u
cd /www/dorm || exit 1
DORM_DATA_DIR=/www/dorm-data .venv/bin/python - <<'PY'
import asyncio
import sys
import time

sys.path.insert(0, '.')
from backend.database import SessionLocal
from backend.services import push_service

db = SessionLocal()
ok = 0
for i in range(6):
    start = time.time()
    token, reason = asyncio.run(push_service.get_access_token(db, force=True))
    cost = time.time() - start
    if token:
        ok += 1
        print(f"  第 {i+1} 次: ✅ 成功（{cost:.1f}s，token 长度 {len(token)}）")
    else:
        print(f"  第 {i+1} 次: ❌ {reason}（{cost:.1f}s）")
    time.sleep(1)

print(f"\n  成功率: {ok}/6")
if ok:
    # 顺手试一次「发消息」调用链（拿真实错误码，不真的发群）
    token, _ = asyncio.run(push_service.get_access_token(db, force=False))
    import httpx
    r = httpx.get('https://api.sgroup.qq.com/v2/users/@me',
                  headers={'Authorization': f'QQBot {token}'}, timeout=15)
    print("  机器人自身信息接口:", r.status_code, r.text[:150])
db.close()
PY
