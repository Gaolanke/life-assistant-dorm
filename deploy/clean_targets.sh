#!/usr/bin/env bash
# 通过新加的图形化接口，删掉两个不用的推送群，只保留当前在用的
set -u
cd /www/dorm || exit 1
export DORM_DATA_DIR=/www/dorm-data

.venv/bin/python - <<'PY'
import asyncio
import sys

sys.path.insert(0, '.')
import httpx

KEEP = "0C06C8CC5A9D4E9D0A7FC80EACACFE6A"
DROP = [
    "0AA8122EF2F56427CBB381D49A6314DC",
    "F5BE1D8CEE82E7EB9D04A95C945569EF",
]

c = httpx.Client(base_url="http://127.0.0.1:8091", timeout=40)
tok = c.post("/api/auth/login", json={"username": "admin", "password": "344940"}).json().get("token", "")
h = {"X-Session-Token": tok}
print(f"登录: {'✅' if tok else '❌'}")

before = c.get("/api/qqbot/groups", headers=h).json()
print(f"\n清理前推送目标: {before.get('configured_groups')!r}")

for openid in DROP:
    r = c.delete(f"/api/qqbot/targets/{openid}", headers=h)
    print(f"\n删除 {openid}")
    print(f"  HTTP {r.status_code}  {r.json().get('message')}")

after = c.get("/api/qqbot/groups", headers=h).json()
print()
print(f"清理后推送目标: {after.get('configured_groups')!r}")
print(f"  已上报群记录 {after.get('total')} 条")

# 给保留的群发一条测试消息，确认可用
from backend.database import SessionLocal
from backend.services import push_service

db = SessionLocal()
result = None
for attempt in range(1, 5):
    result = asyncio.run(push_service.send_group_message(
        db, KEEP, "【生活助手】推送群已整理完成，之后每天的填报汇总会发到这个群。", attempts=1))
    if result.get("ok"):
        print(f"\n发测试消息到保留的群: ✅ 第 {attempt} 次成功")
        break
    print(f"  第 {attempt} 次失败：{str(result.get('message'))[:40]}")
else:
    print(f"\n发测试消息: ❌ {str(result.get('message'))[:50]}")
db.close()
PY
